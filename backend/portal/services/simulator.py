"""
portal/services/simulator.py
============================
Synthetic traffic: normal payments, one fraud story per rule R1-R9, and
stories that combine rules (R1+R4, R3+R6, R5+R8; see COMBOS).

Every story is a short sequence of payments (and, for R9, a login, a new
payee and an OTP request) that SHOULD trigger its rule. Labels:
  - the payment the story is designed to catch -> is_fraud_label = 1
  - the genuine customer's own payment in a story (e.g. the first, home-city
    payment in R3) -> 0
  - build-up payments that are part of the attack but not meant to be caught
    on their own (the first 5 small "card testing" payments in R2, the first
    two structured payments in R7) -> NULL, excluded from metrics.

Each story picks an account whose history makes the target rule the main
signal (e.g. R4 picks a high spender, so a ₹28,000 payment is not also
"unusually large" for them). Some stories still trip a companion rule, as
real fraud does: R7's ₹45,000+ payments are also far above a typical
account's average, and R9's transfers usually come from a new device too.

A ScenarioContext decides *when* (live "now" or a back-dated evaluation
time), *how* payments are submitted (in-process engine or HTTP API) and
records everything created so the evaluator can clean up afterwards.
"""

import hashlib
import random
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta

from portal.extensions import db
from portal.helpers.db_helpers import fetch_all
from portal.helpers.explain import inr
from portal.models import Beneficiary, SessionEvent
from portal.services import fraud_engine, otp_shield

RULE_CODES = ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9"]
CITIES = [
    "Hyderabad", "Bengaluru", "Mumbai", "Delhi", "Chennai", "Pune",
    "Kolkata", "Ahmedabad", "Jaipur", "Lucknow", "Kochi", "Visakhapatnam",
]
FAKE_PAYEES = [
    "Kumar Traders", "Sri Sai Enterprises", "Rapid Refunds Desk", "KYC Update Cell",
    "Lucky Draw Office", "Electricity Board Helpdesk", "Customs Clearance Agent",
]
STORIES = {
    "NORMAL": "A customer buys groceries near home, like any other day.",
    "R1": "A stolen card is used for one very big purchase, far above what the owner normally spends.",
    "R2": "A fraudster tests a stolen card with many small payments in a few minutes.",
    "R3": "The card is used at home, and minutes later in a city hundreds of kilometres away.",
    "R4": "Someone logs in on a brand-new phone and immediately makes a big payment.",
    "R5": "A large payment goes out at 2 o'clock at night while the owner is asleep.",
    "R6": "A payment comes from an internet address already reported for fraud.",
    "R7": "Money is sent as several ₹45,000+ payments to stay under the ₹50,000 check.",
    "R8": "An account unused for over 6 months suddenly sends a large amount.",
    "R9": "A scammer logs in on a new phone, adds a new payee and tries to move money.",
    "R1+R4": "A thief on a brand-new phone makes one purchase many times bigger than the owner ever spends.",
    "R3+R6": "Minutes after the owner pays at home, the card is used in another city from a known fraud IP address.",
    "R5+R8": "An account asleep for over 6 months suddenly sends a large amount at 2 o'clock at night.",
}
# Fraud that trips several rules at once: story code -> the rules it must fire.
COMBOS = {"R1+R4": ["R1", "R4"], "R3+R6": ["R3", "R6"], "R5+R8": ["R5", "R8"]}
FRAUD_SCENARIOS = RULE_CODES + list(COMBOS)

_cache = {"profiles": None, "dormant": None, "merchants": None, "loaded_at": 0.0}
_cache_lock = threading.Lock()
CACHE_SECONDS = 120


def ip_for_device(device_id):
    """A stable home IP per device, so a customer's usual device always
    appears from the same address (seeded history uses the same function)."""
    h = hashlib.sha1(device_id.encode("utf-8")).digest()
    return f"49.{h[0] % 200 + 20}.{h[1] % 254 + 1}.{h[2] % 254 + 1}"


def fraud_ip(rng):
    return f"103.{rng.randint(10, 250)}.{rng.randint(1, 254)}.{rng.randint(1, 254)}"


# --------------------------------------------------------------------------
# Account profiles (cached; refreshed every 2 minutes)
# --------------------------------------------------------------------------


def _load_profiles():
    rows = fetch_all(
        """
        SELECT a.id AS account_id, a.account_no, c.id AS customer_id, c.name, c.home_city,
               c.typical_amount, c.active_from_hour, c.active_to_hour, c.usual_channels,
               COALESCE(s.avg90, 0) AS avg90, COALESCE(s.cnt90, 0) AS cnt90,
               d.devices
          FROM accounts a
          JOIN customers c ON c.id = a.customer_id
          LEFT JOIN (SELECT account_id, AVG(amount) AS avg90, COUNT(*) AS cnt90
                       FROM transactions
                      WHERE status = 'APPROVED' AND txn_time >= NOW() - INTERVAL 90 DAY
                      GROUP BY account_id) s ON s.account_id = a.id
          JOIN (SELECT account_id, GROUP_CONCAT(device_id ORDER BY id) AS devices
                  FROM devices WHERE is_trusted = 1 GROUP BY account_id) d ON d.account_id = a.id
         WHERE a.status = 'ACTIVE'
           AND (c.netbanking_id IS NULL OR c.netbanking_id <> 'ravi.kumar')
           AND NOT EXISTS (SELECT 1 FROM customer_users cu WHERE cu.customer_id = c.id)
        """
    )
    profiles, dormant = [], []
    for r in rows:
        r["typical_amount"] = float(r["typical_amount"])
        r["avg90"] = float(r["avg90"])
        r["devices"] = r["devices"].split(",")
        r["channels"] = r["usual_channels"].split(",")
        if r["cnt90"] >= 3:
            profiles.append(r)
    dormant = fetch_all(
        """
        SELECT a.id AS account_id, a.account_no, c.id AS customer_id, c.name, c.home_city,
               (SELECT d.device_id FROM devices d
                 WHERE d.account_id = a.id AND d.is_trusted = 1 ORDER BY d.id LIMIT 1) AS device
          FROM accounts a JOIN customers c ON c.id = a.customer_id
         WHERE (a.status = 'DORMANT' OR COALESCE(a.last_txn_at, a.opened_on) < NOW() - INTERVAL 200 DAY)
           AND NOT EXISTS (SELECT 1 FROM customer_users cu WHERE cu.customer_id = c.id)
        """
    )
    merchants = fetch_all("SELECT id, name, category, city, risk_level FROM merchants WHERE risk_level <> 'HIGH'")
    by_city = defaultdict(list)
    for m in merchants:
        by_city[m["city"]].append(m)
    return profiles, dormant, {"all": merchants, "by_city": by_city}


def get_cache(force=False):
    with _cache_lock:
        if force or _cache["profiles"] is None or time.time() - _cache["loaded_at"] > CACHE_SECONDS:
            p, d, m = _load_profiles()
            _cache.update(profiles=p, dormant=d, merchants=m, loaded_at=time.time())
        return _cache


def _merchant(rng, city, categories=None):
    m = get_cache()["merchants"]
    pool = m["by_city"].get(city) or m["all"]
    if categories:
        pool = [x for x in pool if x["category"] in categories] or [x for x in m["all"] if x["category"] in categories] or pool
    return rng.choice(pool)


# --------------------------------------------------------------------------
# Context
# --------------------------------------------------------------------------


class ScenarioContext:
    """When, how and by whom a scenario's payments are submitted."""

    def __init__(self, source="SIMULATOR", base_time=None, live=True, rng=None, submit=None, prefix="SIM"):
        self.source = source
        self.base_time = base_time or datetime.now()
        self.live = live
        self.rng = rng or random.Random()
        self.submit_fn = submit
        self.prefix = prefix
        self.created = defaultdict(list)
        self.results = []

    def ref(self, tag):
        return f"{self.prefix}-{tag}-{uuid.uuid4().hex[:14]}"

    def submit(self, payload, label, scenario):
        payload.update(is_fraud_label=label, scenario=scenario, source=self.source)
        if self.submit_fn:
            result = self.submit_fn(payload)
        else:
            result = fraud_engine.ingest(payload, source=self.source)
        self.created["txn_ids"].append(result["txn_id"])
        self.created["accounts"].append(payload["account_id"])
        self.results.append({"label": label, "scenario": scenario, "result": result, "payload": dict(payload)})
        return result

    def add_session(self, account_id, event, device_id, ip, city, at):
        s = SessionEvent(account_id=account_id, device_id=device_id, ip_address=ip, city=city,
                         event_type=event, created_at=at)
        db.session.add(s)
        db.session.flush()
        self.created["sessions"].append(s.id)
        return s

    def add_payee(self, account_id, name, device_id, at):
        b = Beneficiary(
            account_id=account_id,
            payee_name=name,
            payee_account_no=str(self.rng.randint(10**13, 10**14 - 1)),
            payee_ifsc=f"SBIN0{self.rng.randint(100000, 999999)}",
            added_at=at,
            added_device_id=device_id,
        )
        db.session.add(b)
        db.session.flush()
        self.created["beneficiaries"].append(b.id)
        return b


def _payment(ctx, profile, amount, at, channel=None, city=None, device=None, ip=None, merchant=None,
             beneficiary_id=None, tag="P"):
    city = city or profile["home_city"]
    device = device or profile["devices"][0]
    channel = channel or ctx.rng.choice(profile["channels"])
    if merchant is None and beneficiary_id is None and channel != "ATM":
        merchant = _merchant(ctx.rng, city)
    return {
        "external_ref": ctx.ref(tag),
        "account_id": profile["account_id"],
        "merchant_id": merchant["id"] if merchant else None,
        "beneficiary_id": beneficiary_id,
        "amount": round(amount, 2),
        "channel": channel,
        "city": city,
        "device_id": device,
        "ip_address": ip or ip_for_device(device),
        "txn_time": at,
    }


def _pick(ctx, min_avg=None, max_avg=None, exclude=None):
    profiles = get_cache()["profiles"]
    if not profiles:
        raise RuntimeError("No customers with history found. Run `flask seed` first.")
    pool = [
        p for p in profiles
        if (min_avg is None or p["avg90"] >= min_avg)
        and (max_avg is None or p["avg90"] <= max_avg)
        and (not exclude or p["account_id"] not in exclude)
    ]
    return ctx.rng.choice(pool or profiles)


def _daytime(ctx, at):
    """Live: now. Evaluation: the base day at a normal waking hour."""
    if ctx.live:
        return at
    t = at.replace(hour=ctx.rng.randint(10, 19), minute=ctx.rng.randint(0, 59), second=ctx.rng.randint(0, 59))
    return t if t <= datetime.now() else t - timedelta(days=1)


def _normal_amount(rng, profile):
    factor = min(2.5, max(0.15, rng.lognormvariate(-0.1, 0.45)))
    return max(20.0, profile["typical_amount"] * factor)


# --------------------------------------------------------------------------
# Normal traffic and the nine fraud stories
# --------------------------------------------------------------------------


def normal_payment(ctx, profile=None):
    rng = ctx.rng
    profile = profile or _pick(ctx)
    at = ctx.base_time
    if not ctx.live:
        lo, hi = profile["active_from_hour"], max(profile["active_from_hour"] + 1, profile["active_to_hour"])
        at = at.replace(hour=rng.randint(lo, hi - 1), minute=rng.randint(0, 59), second=rng.randint(0, 59))
        if at > datetime.now():
            at -= timedelta(days=1)
    device = rng.choice(profile["devices"])
    return ctx.submit(_payment(ctx, profile, _normal_amount(rng, profile), at, device=device, tag="N"), 0, "NORMAL")


def scenario_r1(ctx):
    p = _pick(ctx, min_avg=1500)
    at = _daytime(ctx, ctx.base_time)
    amount = min(24000.0, p["avg90"] * ctx.rng.uniform(8, 14))
    if amount <= 5 * p["avg90"]:
        amount = p["avg90"] * 8
    m = _merchant(ctx.rng, p["home_city"], ["Electronics", "Jewellery", "Online Shopping"])
    return ctx.submit(_payment(ctx, p, amount, at, channel="CARD", merchant=m, tag="R1"), 1, "R1")


def scenario_r2(ctx):
    p = _pick(ctx)
    end = _daytime(ctx, ctx.base_time)
    m = _merchant(ctx.rng, p["home_city"], ["Online Shopping", "Entertainment"])
    last = None
    for i in range(6):
        at = end - timedelta(minutes=5 - i, seconds=ctx.rng.randint(0, 20))
        label = 1 if i == 5 else None
        last = ctx.submit(
            _payment(ctx, p, ctx.rng.uniform(99, 499), at, channel="CARD", merchant=m, tag="R2"), label, "R2"
        )
    return last


def scenario_r3(ctx):
    p = _pick(ctx)
    end = _daytime(ctx, ctx.base_time)
    gap = ctx.rng.randint(6, 20)
    ctx.submit(_payment(ctx, p, _normal_amount(ctx.rng, p), end - timedelta(minutes=gap), channel="CARD", tag="R3H"), 0, "R3")
    far = ctx.rng.choice([c for c in CITIES if c != p["home_city"]])
    stolen = f"{ctx.prefix}-CARDSKIM-{uuid.uuid4().hex[:8]}"
    amount = min(20000.0, max(500.0, _normal_amount(ctx.rng, p)))
    return ctx.submit(
        _payment(ctx, p, amount, end, channel="CARD", city=far, device=stolen, ip=fraud_ip(ctx.rng), tag="R3"),
        1, "R3",
    )


def scenario_r4(ctx):
    p = _pick(ctx, min_avg=5600)
    at = _daytime(ctx, ctx.base_time)
    top = max(26000.0, min(45000.0, p["avg90"] * 4.8))
    amount = ctx.rng.uniform(25500, top)
    device = f"{ctx.prefix}-NEWPHONE-{uuid.uuid4().hex[:8]}"
    ctx.created["devices"].append(device)
    m = _merchant(ctx.rng, p["home_city"], ["Electronics", "Jewellery", "Travel"])
    return ctx.submit(
        _payment(ctx, p, amount, at, channel="UPI", device=device, ip=fraud_ip(ctx.rng), merchant=m, tag="R4"),
        1, "R4",
    )


def scenario_r5(ctx):
    p = _pick(ctx, min_avg=2400)
    at = _night(ctx, ctx.base_time)
    amount = ctx.rng.uniform(10500, max(10600.0, min(24000.0, p["avg90"] * 4.7)))
    return ctx.submit(_payment(ctx, p, amount, at, channel="UPI", tag="R5"), 1, "R5")


def scenario_r6(ctx):
    p = _pick(ctx)
    at = _daytime(ctx, ctx.base_time)
    bad = fetch_all("SELECT entry_type, entry_value FROM watchlist WHERE entry_type IN ('IP', 'DEVICE')")
    ip = device = None
    if bad:
        pick = ctx.rng.choice(bad)
        if pick["entry_type"] == "IP":
            ip = pick["entry_value"]
        else:
            device = pick["entry_value"]
    return ctx.submit(
        _payment(ctx, p, _normal_amount(ctx.rng, p), at, channel="UPI", device=device, ip=ip, tag="R6"), 1, "R6"
    )


def scenario_r7(ctx):
    p = _pick(ctx)
    end = _daytime(ctx, ctx.base_time)
    if ctx.live:
        offsets = [timedelta(minutes=2), timedelta(minutes=1), timedelta(0)]
    else:
        h1 = ctx.rng.randint(8, 20)
        offsets = [timedelta(hours=h1), timedelta(hours=ctx.rng.randint(1, max(1, h1 - 1))), timedelta(0)]
    m = _merchant(ctx.rng, p["home_city"], ["Jewellery", "Electronics"])
    last = None
    for i, off in enumerate(offsets):
        label = 1 if i == 2 else None
        last = ctx.submit(
            _payment(ctx, p, ctx.rng.uniform(45000, 49999), end - off, channel="NETBANKING", merchant=m, tag="R7"),
            label, "R7",
        )
    return last


def scenario_r8(ctx):
    dormant = get_cache()["dormant"]
    if not dormant:
        raise RuntimeError("No dormant accounts found. Run `flask seed` first.")
    d = ctx.rng.choice(dormant)
    at = _daytime(ctx, ctx.base_time)
    profile = {
        "account_id": d["account_id"],
        "home_city": d["home_city"],
        "devices": [d["device"] or f"{ctx.prefix}-OLDPHONE-{d['account_id']}"],
        "channels": ["NETBANKING"],
    }
    return ctx.submit(_payment(ctx, profile, ctx.rng.uniform(25000, 60000), at, channel="NETBANKING", tag="R8"), 1, "R8")


def scenario_r9(ctx):
    """The OTP-scam story: new-device login -> new payee -> OTP request
    (R9-A) -> transfer (R9-B)."""
    p = _pick(ctx)
    end = _daytime(ctx, ctx.base_time)
    device = f"{ctx.prefix}-SCAMPHONE-{uuid.uuid4().hex[:8]}"
    ctx.created["devices"].append(device)
    city = ctx.rng.choice([c for c in CITIES if c != p["home_city"]])
    ip = fraud_ip(ctx.rng)
    ctx.add_session(p["account_id"], "LOGIN", device, ip, city, end - timedelta(minutes=ctx.rng.randint(4, 9)))
    payee = ctx.add_payee(p["account_id"], ctx.rng.choice(FAKE_PAYEES), device, end - timedelta(minutes=ctx.rng.randint(2, 3)))
    amount = round(ctx.rng.uniform(12000, 48000), 2)
    db.session.commit()
    shield = otp_shield.request_otp(p["account_id"], payee.id, amount, device, ip, city, at=end - timedelta(seconds=40))
    ctx.created["otp_requests"].append(shield["otp_request_id"])
    ctx.created["sessions"].extend(
        r["id"] for r in fetch_all(
            "SELECT id FROM sessions WHERE account_id = :a AND device_id = :d AND event_type = 'OTP_REQUEST'",
            {"a": p["account_id"], "d": device},
        )
    )
    # The attacker pushes the transfer anyway (e.g. through a compromised
    # channel). Rule R9 inside the stored procedure is the safety net.
    result = ctx.submit(
        _payment(ctx, p, amount, end, channel="NETBANKING", city=city, device=device, ip=ip,
                 beneficiary_id=payee.id, tag="R9"),
        1, "R9",
    )
    result["otp_shield"] = {k: shield[k] for k in ("decision", "risk_points", "signals")}
    return result


def _night(ctx, base):
    """Live before 5 am: now. Otherwise 1-3 am on the base day."""
    if ctx.live and base.hour < 5:
        return base
    at = base.replace(hour=ctx.rng.randint(1, 3), minute=ctx.rng.randint(0, 59), second=ctx.rng.randint(0, 59))
    return at - timedelta(days=1) if at > datetime.now() else at


def scenario_r1_r4(ctx):
    """Stolen phone + card: a new device AND an amount far above usual."""
    p = _pick(ctx, min_avg=1500, max_avg=5500)
    at = _daytime(ctx, ctx.base_time)
    amount = max(26000.0, p["avg90"] * ctx.rng.uniform(6, 9))
    device = f"{ctx.prefix}-NEWPHONE-{uuid.uuid4().hex[:8]}"
    ctx.created["devices"].append(device)
    m = _merchant(ctx.rng, p["home_city"], ["Electronics", "Jewellery"])
    return ctx.submit(
        _payment(ctx, p, amount, at, channel="UPI", device=device, ip=fraud_ip(ctx.rng), merchant=m, tag="R1R4"),
        1, "R1+R4",
    )


def scenario_r3_r6(ctx):
    """Cloned card used far away, from an IP address already reported."""
    p = _pick(ctx)
    end = _daytime(ctx, ctx.base_time)
    ctx.submit(_payment(ctx, p, _normal_amount(ctx.rng, p), end - timedelta(minutes=ctx.rng.randint(6, 20)),
                        channel="CARD", tag="R3R6H"), 0, "R3+R6")
    bad_ips = fetch_all("SELECT entry_value FROM watchlist WHERE entry_type = 'IP'")
    ip = ctx.rng.choice(bad_ips)["entry_value"] if bad_ips else fraud_ip(ctx.rng)
    far = ctx.rng.choice([c for c in CITIES if c != p["home_city"]])
    stolen = f"{ctx.prefix}-CARDSKIM-{uuid.uuid4().hex[:8]}"
    amount = min(20000.0, max(500.0, _normal_amount(ctx.rng, p)))
    return ctx.submit(
        _payment(ctx, p, amount, end, channel="CARD", city=far, device=stolen, ip=ip, tag="R3R6"), 1, "R3+R6"
    )


def scenario_r5_r8(ctx):
    """A dormant account drained in the middle of the night."""
    dormant = get_cache()["dormant"]
    if not dormant:
        raise RuntimeError("No dormant accounts found. Run `flask seed` first.")
    d = ctx.rng.choice(dormant)
    profile = {
        "account_id": d["account_id"],
        "home_city": d["home_city"],
        "devices": [d["device"] or f"{ctx.prefix}-OLDPHONE-{d['account_id']}"],
        "channels": ["NETBANKING"],
    }
    at = _night(ctx, ctx.base_time)
    return ctx.submit(
        _payment(ctx, profile, ctx.rng.uniform(25000, 60000), at, channel="NETBANKING", tag="R5R8"), 1, "R5+R8"
    )


SCENARIOS = {
    "NORMAL": normal_payment,
    "R1": scenario_r1, "R2": scenario_r2, "R3": scenario_r3, "R4": scenario_r4, "R5": scenario_r5,
    "R6": scenario_r6, "R7": scenario_r7, "R8": scenario_r8, "R9": scenario_r9,
    "R1+R4": scenario_r1_r4, "R3+R6": scenario_r3_r6, "R5+R8": scenario_r5_r8,
}


def expected_rules(code):
    """The rules a story is built to fire ([] for NORMAL)."""
    return COMBOS.get(code, [] if code == "NORMAL" else [code])


def run_scenario(code, ctx=None):
    """Runs one story and returns what happened, for the Fraud Lab."""
    code = code.upper()
    if code not in SCENARIOS:
        raise KeyError(code)
    ctx = ctx or ScenarioContext()
    target = SCENARIOS[code](ctx)
    expected = expected_rules(code)
    fired = [h["rule_code"] for h in target["rules"]]
    return {
        "scenario": code,
        "story": STORIES[code],
        "expected_rule": "+".join(expected) or None,
        "expected_rules": expected,
        "expected_rule_fired": all(r in fired for r in expected) if expected else (target["status"] == "APPROVED"),
        "target": target,
        "steps": [
            {
                "txn_id": r["result"]["txn_id"],
                "amount": r["result"]["amount"],
                "status": r["result"]["status"],
                "risk_score": r["result"]["risk_score"],
                "rules": [h["rule_code"] for h in r["result"]["rules"]],
                "label": r["label"],
            }
            for r in ctx.results
        ],
        "summary": (
            f"{inr(target['amount'])} → {target['status']} (risk {target['risk_score']}/100), "
            f"rules fired: {', '.join(fired) or 'none'}"
        ),
    }


# --------------------------------------------------------------------------
# Live stream (Fraud Lab "Start live traffic")
# --------------------------------------------------------------------------


class StreamManager:
    """Background thread producing live traffic at `rate` payments/second.

    Each account is used at most once every ACCOUNT_SPACING seconds: real
    customers don't pay every few seconds, and doing so would (correctly)
    trip rule R2. With ~280 demo accounts that caps normal traffic at about
    2 payments/second; a higher requested rate runs as fast as that allows.
    """

    ACCOUNT_SPACING = 150

    def __init__(self):
        self._thread = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.rate = 2.0
        self.fraud_ratio = 0.03
        self.stats = {"started_at": None, "sent": 0, "fraud": 0, "approved": 0, "review": 0, "blocked": 0, "errors": 0}

    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, app, rate=2.0, fraud_ratio=0.03):
        with self._lock:
            self.rate, self.fraud_ratio = rate, fraud_ratio
            if self.running():
                return self.status()
            self._stop.clear()
            self.stats = {"started_at": datetime.now().isoformat(), "sent": 0, "fraud": 0,
                          "approved": 0, "review": 0, "blocked": 0, "errors": 0}
            self._thread = threading.Thread(target=self._run, args=(app,), name="fraudshield-stream", daemon=True)
            self._thread.start()
        return self.status()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        return self.status()

    def status(self):
        return {"running": self.running(), "rate": self.rate, "fraud_ratio": self.fraud_ratio, **self.stats}

    def _record(self, result):
        self.stats["sent"] += 1
        key = result["status"].lower()
        if key in self.stats:
            self.stats[key] += 1

    def _run(self, app):
        rng = random.Random()
        last_used = {}
        with app.app_context():
            app.logger.info("Live traffic stream started at %.1f/s", self.rate)
            while not self._stop.is_set():
                tick = time.time()
                try:
                    ctx = ScenarioContext(source="SIMULATOR", live=True, rng=rng, prefix="LIVE")
                    if rng.random() < self.fraud_ratio:
                        codes = [c for c in FRAUD_SCENARIOS if "R5" not in c or datetime.now().hour < 5]
                        result = SCENARIOS[rng.choice(codes)](ctx)
                        self.stats["fraud"] += 1
                    else:
                        now = time.time()
                        free = [p for p in get_cache()["profiles"]
                                if now - last_used.get(p["account_id"], 0) > self.ACCOUNT_SPACING]
                        if not free:
                            self._stop.wait(0.5)
                            continue
                        profile = rng.choice(free)
                        last_used[profile["account_id"]] = now
                        result = normal_payment(ctx, profile)
                    self._record(result)
                except Exception:
                    db.session.rollback()
                    self.stats["errors"] += 1
                    app.logger.exception("Stream payment failed")
                finally:
                    db.session.remove()
                elapsed = time.time() - tick
                self._stop.wait(max(0.0, 1.0 / max(self.rate, 0.1) - elapsed))
            app.logger.info("Live traffic stream stopped after %s payments", self.stats["sent"])


STREAM = StreamManager()


def clear_cache():
    """Forces the profile cache to reload on next use (after seeding)."""
    with _cache_lock:
        _cache["profiles"] = None
