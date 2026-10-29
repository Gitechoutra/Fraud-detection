"""
portal/services/attacker.py
===========================
The fraudster simulation console (/attacker) -- SIMULATION ONLY.

Each button plays one fraud pattern against a demo customer whose
credentials the logged-in fraudster "stole" (stolen_credentials). Nothing is
decided here: every payment is submitted through fraud_engine.ingest, so
sp_evaluate_transaction fires the rules and makes the decision, services/funds
moves or holds the money, and the victim gets the alert in their banking app.
The R9 attack also asks OTP Shield for an OTP exactly as the bank app does.

The console cannot be used as a free-form attack tool: amounts, payees,
devices and timing are chosen here from fixed demo settings; the fraudster
only picks which pattern to play. Time-dependent patterns use a controlled
simulation clock -- the payment's txn_time is set on the server (e.g. 02:15
for the late-night rule, a few minutes apart for card testing) -- and the
rules themselves are untouched.
"""

import random
import uuid
from datetime import datetime, timedelta

from portal.extensions import db
from portal.helpers.db_helpers import fetch_all, fetch_one, scalar
from portal.helpers.explain import inr
from portal.helpers.responses import AppError
from portal.models import AttackEvent, Beneficiary, SessionEvent
from portal.services import fraud_engine, otp_shield
from portal.services.simulator import CITIES, ip_for_device

SOURCE = "ATTACK_SIM"
MULE = {"payee_name": "QuickCash Traders", "payee_account_no": "99887766554433", "payee_ifsc": "YESB0009911"}

SCENARIOS = {
    "R1": {"title": "Large-amount transaction", "rules": ["R1"], "victims": ["ravi", "suresh", "arjun"],
           "story": "Uses the stolen card for one purchase many times bigger than the owner ever spends."},
    "R2": {"title": "Card testing", "rules": ["R2"], "victims": ["arjun", "suresh", "ravi", "priya"],
           "story": "Fires six tiny online payments in five minutes to check the stolen card works."},
    "R3": {"title": "Cloned card in another city", "rules": ["R3"], "victims": ["ravi", "priya", "suresh", "arjun"],
           "story": "Minutes after the owner pays at home, a skimmed copy of the card is used in the fraudster's city."},
    "R4": {"title": "New phone, big payment", "rules": ["R4"], "victims": ["priya"],
           "story": "Logs in from the fraudster's own phone and makes a big UPI payment."},
    "R5": {"title": "Midnight transfer", "rules": ["R5"], "victims": ["ravi", "priya"],
           "story": "Spends with the stolen card at 2:15 at night while the owner is asleep."},
    "R6": {"title": "Transfer to a mule account", "rules": ["R6"], "victims": ["suresh", "arjun", "ravi", "priya"],
           "story": "Adds the gang's mule account as a payee and sends money to it."},
    "R7": {"title": "Split payments", "rules": ["R7"], "victims": ["priya"],
           "story": "Splits a big amount into three payments just under ₹50,000 within three hours."},
    "R8": {"title": "Sleeping account", "rules": ["R8"], "victims": ["lakshmi"],
           "story": "After a SIM swap, drains an account nobody has used for months."},
    "R9": {"title": "Phishing link + OTP call", "rules": ["R9"], "victims": ["ravi", "priya", "suresh", "arjun"],
           "story": "Logs in with the phished password, adds a new payee, asks for the OTP and calls the victim for it."},
    "COMBINED": {"title": "Combined attack", "rules": ["R3", "R2", "R6", "R9"], "victims": ["ravi", "priya", "suresh", "arjun"],
                 "story": "Clones the card, tests it, then takes over net banking and empties the account into the mule."},
}


# --------------------------------------------------------------------------
# Who, from where
# --------------------------------------------------------------------------


def credentials(fraudster_id):
    """What the fraudster holds -- never passwords, hashes or full numbers."""
    rows = fetch_all(
        """
        SELECT sc.id, sc.obtained_via, sc.obtained_at, cu.username, cu.card_last4, c.name, c.home_city,
               a.account_no, a.status
          FROM stolen_credentials sc
          JOIN customer_users cu ON cu.customer_id = sc.customer_id
          JOIN customers c ON c.id = sc.customer_id
          JOIN accounts a ON a.customer_id = c.id
         WHERE sc.fraudster_id = :f
         ORDER BY cu.username
        """, {"f": fraudster_id})
    return [{
        "id": r["id"], "victim": r["name"], "username": r["username"], "home_city": r["home_city"],
        "account": "XXXX" + r["account_no"][-4:], "card": f"•••• {r['card_last4']}" if r["card_last4"] else None,
        "password": "•••••••• (stolen)", "obtained_via": r["obtained_via"], "obtained_at": r["obtained_at"].isoformat(),
        "account_status": r["status"],
    } for r in rows]


def _victim(fraudster_id, code):
    usernames = SCENARIOS[code]["victims"]
    marks = ", ".join(f":u{i}" for i in range(len(usernames)))
    rows = fetch_all(
        f"""
        SELECT cu.username, cu.card_last4, c.id AS customer_id, c.name, c.home_city, c.typical_amount,
               a.id AS account_id, a.balance - a.held_amount AS available,
               (SELECT d.device_id FROM devices d WHERE d.account_id = a.id AND d.is_trusted = 1 ORDER BY d.id LIMIT 1)
                   AS phone
          FROM stolen_credentials sc
          JOIN customer_users cu ON cu.customer_id = sc.customer_id
          JOIN customers c ON c.id = sc.customer_id
          JOIN accounts a ON a.customer_id = c.id
         WHERE sc.fraudster_id = :f AND cu.username IN ({marks})
        """, {"f": fraudster_id, **{f"u{i}": u for i, u in enumerate(usernames)}})
    by_name = {r["username"]: r for r in rows}
    for username in usernames:
        if username in by_name:
            v = by_name[username]
            v["card"] = f"CARD-{v['card_last4']}"
            v["avg90"] = float(scalar(
                "SELECT COALESCE(AVG(amount), 0) FROM transactions WHERE account_id = :a AND status = 'APPROVED' "
                "AND txn_time >= NOW() - INTERVAL 90 DAY", {"a": v["account_id"]}) or v["typical_amount"])
            return v
    raise AppError(f"You hold no stolen credentials that fit this attack (needs: {', '.join(usernames)}).",
                   "NO_SUITABLE_VICTIM", 409)


def _merchant(city, categories):
    marks = ", ".join(f":c{i}" for i in range(len(categories)))
    row = fetch_one(f"SELECT id FROM merchants WHERE city = :city AND category IN ({marks}) AND risk_level <> 'HIGH' "
                    "ORDER BY RAND() LIMIT 1", {"city": city, **{f"c{i}": c for i, c in enumerate(categories)}})
    row = row or fetch_one("SELECT id FROM merchants WHERE city = :city AND risk_level <> 'HIGH' ORDER BY RAND() LIMIT 1",
                           {"city": city})
    return row["id"] if row else None


class Attack:
    def __init__(self, fraudster, code, device, ip, city):
        self.fraudster, self.code = fraudster, code
        self.device, self.ip = device, ip
        self.city = city
        self.now = datetime.now()
        self.rng = random.Random()
        self.victim = _victim(fraudster.id, code)
        if self.city == self.victim["home_city"]:
            self.city = next(c for c in CITIES if c != self.victim["home_city"])
        self.steps = []

    def pay(self, label, attack=True, **fields):
        payload = {
            "external_ref": f"ATK-{self.code}-{uuid.uuid4().hex[:12]}",
            "account_id": self.victim["account_id"],
            "channel": "CARD", "city": self.victim["home_city"], "device_id": self.device, "ip_address": self.ip,
            "txn_time": self.now, "source": SOURCE,
        }
        payload.update(fields)
        payload["amount"] = round(payload["amount"], 2)
        try:
            res = fraud_engine.ingest(payload, source=SOURCE)
        except AppError as exc:  # e.g. not enough balance: the bank refuses it
            self.steps.append({"label": label, "attack": attack, "error": exc.message, "code": exc.code,
                               "amount": float(payload["amount"])})
            return None
        if attack:
            db.session.add(AttackEvent(fraudster_id=self.fraudster.id, customer_id=self.victim["customer_id"],
                                       txn_id=res["txn_id"], scenario=self.code, step=label[:160]))
            db.session.commit()
        self.steps.append({"label": label, "attack": attack, **_decision(res)})
        return res

    def phished_login(self, minutes_ago=4):
        db.session.add(SessionEvent(account_id=self.victim["account_id"], device_id=self.device, ip_address=self.ip,
                                    city=self.city, event_type="LOGIN",
                                    created_at=self.now - timedelta(minutes=minutes_ago)))
        db.session.commit()
        self.steps.append({"label": f"Logs in to {self.victim['name']}'s net banking with the phished password "
                                    f"from a new phone in {self.city}", "attack": True, "info": True})

    def add_payee(self, payee_name, payee_account_no, payee_ifsc, minutes_ago=2, reuse=False):
        payee = Beneficiary.query.filter_by(account_id=self.victim["account_id"],
                                            payee_account_no=payee_account_no).first() if reuse else None
        if payee is None:
            payee = Beneficiary(account_id=self.victim["account_id"], payee_name=payee_name,
                                payee_account_no=payee_account_no, payee_ifsc=payee_ifsc,
                                added_at=self.now - timedelta(minutes=minutes_ago), added_device_id=self.device)
            db.session.add(payee)
            db.session.commit()
            self.steps.append({"label": f"Adds a new payee: {payee_name}", "attack": True, "info": True})
        return payee


def _decision(res):
    return {
        "txn_id": res["txn_id"], "external_ref": res["external_ref"], "amount": res["amount"],
        "status": res["status"], "risk_score": res["risk_score"], "funds_status": res.get("funds_status"),
        "rules": [{"rule_code": h["rule_code"], "detail_text": h["detail_text"], "weight": h["weight_applied"]}
                  for h in res["rules"]],
        "duplicate": res.get("duplicate", False),
    }


# --------------------------------------------------------------------------
# The patterns
# --------------------------------------------------------------------------


def _r1(a):
    v = a.victim
    amount = min(24000.0, v["avg90"] * 8)
    if amount <= v["avg90"] * 5:
        raise AppError("This victim spends too much for a large-amount attack to stand out.", "NO_SUITABLE_VICTIM", 409)
    a.pay(f"Buys electronics for {inr(amount)} with the stolen card ({amount / v['avg90']:.1f}× usual)",
          amount=amount, device_id=v["card"], merchant_id=_merchant(v["home_city"], ["Electronics", "Jewellery"]))


def _r2(a):
    v = a.victim
    merchant = _merchant(v["home_city"], ["Online Shopping", "Entertainment"])
    for i in range(6):
        amount = a.rng.uniform(99, 499)
        a.pay(f"Card test {i + 1} of 6: {inr(amount)} online", amount=amount, device_id=v["card"], merchant_id=merchant,
              txn_time=a.now - timedelta(minutes=5 - i, seconds=a.rng.randint(0, 20)))


def _r3(a, gap_minutes=12):
    v = a.victim
    a.pay(f"{v['name']} pays at home in {v['home_city']} (the real card)", attack=False,
          amount=max(300.0, v["avg90"] * 0.6), device_id=v["card"], ip_address=ip_for_device(v["phone"] or v["card"]),
          merchant_id=_merchant(v["home_city"], ["Grocery", "Restaurants"]), txn_time=a.now - timedelta(minutes=gap_minutes))
    amount = min(20000.0, max(1500.0, v["avg90"] * 1.5))
    a.pay(f"{gap_minutes} minutes later the cloned card is used in {a.city}", amount=amount, city=a.city,
          device_id=f"SKIM-{a.fraudster.username.upper()}-{uuid.uuid4().hex[:6]}",
          merchant_id=_merchant(a.city, ["Electronics", "Clothing", "Jewellery"]))


def _r4(a):
    v = a.victim
    amount = min(max(26000.0, v["avg90"] * 3.5), v["avg90"] * 4.8)
    if amount <= 25000:
        raise AppError("This victim's usual spending is too low for this pattern.", "NO_SUITABLE_VICTIM", 409)
    a.pay(f"From the fraudster's own phone in {a.city}: {inr(amount)} by UPI", amount=amount, channel="UPI",
          city=a.city, merchant_id=_merchant(a.city, ["Electronics", "Travel"]))


def _r5(a):
    v = a.victim
    at = a.now.replace(hour=2, minute=15, second=0, microsecond=0)
    if at > a.now:
        at -= timedelta(days=1)
    amount = min(11000.0, v["avg90"] * 4.6)
    a.pay(f"At 2:15 at night the stolen card buys jewellery for {inr(amount)} (simulation clock)", amount=amount,
          device_id=v["card"], txn_time=at, merchant_id=_merchant(v["home_city"], ["Jewellery", "Electronics"]))


def _r6(a, amount=8000.0, login=False):
    if login:
        a.phished_login()
    payee = a.add_payee(**MULE, reuse=True)
    a.pay(f"Sends {inr(amount)} to the mule account {MULE['payee_name']}", amount=amount, channel="NETBANKING",
          city=a.city, beneficiary_id=payee.id)


def _r7(a):
    v = a.victim
    merchant = _merchant(v["home_city"], ["Jewellery", "Electronics"])
    for i, hours in enumerate((2, 1, 0)):
        amount = a.rng.uniform(45500, 49500)
        a.pay(f"Split payment {i + 1} of 3: {inr(amount)}, just under ₹50,000", amount=amount, device_id=v["card"],
              merchant_id=merchant, txn_time=a.now - timedelta(hours=hours, minutes=a.rng.randint(0, 9) if hours else 0))


def _r8(a):
    a.pay(f"After a SIM swap, takes {inr(22000)} from an account asleep for months", amount=22000.0,
          channel="NETBANKING", city=a.city, merchant_id=_merchant(a.city, ["Travel", "Electronics"]))


def _r9(a, amount=18000.0, payee=None):
    v = a.victim
    a.phished_login()
    payee = payee or a.add_payee(a.rng.choice(["Kumar Traders", "KYC Update Cell", "Lucky Draw Office"]),
                                 str(a.rng.randint(10**13, 10**14 - 1)), f"PUNB0{a.rng.randint(100000, 999999)}")
    try:
        shield = otp_shield.request_otp(v["account_id"], payee.id, amount, a.device, a.ip, a.city,
                                        at=a.now - timedelta(seconds=40))
    except AppError as exc:  # payee on hold, too many OTP requests, ...
        a.steps.append({"label": f"Asks for an OTP: OTP Shield refuses — {exc.message}", "attack": True, "info": True})
        a.pay(f"Pushes {inr(amount)} to {payee.payee_name} through a compromised channel anyway", amount=amount,
              channel="NETBANKING", city=a.city, beneficiary_id=payee.id)
        return
    if shield["decision"] == "OTP_BLOCKED_APPROVAL_REQUIRED":
        a.steps.append({"label": f"Asks for an OTP: OTP Shield refuses to create one ({shield['risk_points']} risk "
                                 "points) and asks the real customer's phone instead", "attack": True, "info": True,
                        "otp_shield": shield["decision"]})
        a.steps.append({"label": f"Calls {v['name']} pretending to be the bank — there is no OTP to give, so "
                                 "the fraudster pushes the transfer through anyway", "attack": True, "info": True})
        a.pay(f"Transfers {inr(amount)} to {payee.payee_name}", amount=amount, channel="NETBANKING", city=a.city,
              beneficiary_id=payee.id, otp_request_id=shield["otp_request_id"])
        return
    # An OTP was sent to the victim's phone: the "bank officer" on the call
    # talks them into reading it out, and the fraudster types it.
    sms = fetch_one("SELECT body FROM notifications WHERE kind = 'OTP' AND ref_id = :r ORDER BY id DESC LIMIT 1",
                    {"r": shield["otp_request_id"]})
    otp = next((w for w in sms["body"].split() if w.isdigit() and len(w) == 6), None) if sms else None
    a.steps.append({"label": f"Asks for an OTP: OTP Shield sends it with a warning ({shield['decision']}); on the "
                             f"phone call {v['name']} is tricked into reading it out", "attack": True, "info": True,
                    "otp_shield": shield["decision"]})
    out = otp_shield.verify_otp(shield["otp_request_id"], otp, a.device, account_id=v["account_id"],
                                ip_address=a.ip, city=a.city)
    res = out["payment"]
    db.session.add(AttackEvent(fraudster_id=a.fraudster.id, customer_id=v["customer_id"], txn_id=res["txn_id"],
                               scenario=a.code, step="Transfer with the OTP read out on the call"))
    db.session.commit()
    a.steps.append({"label": f"Types the OTP and transfers {inr(amount)} to {payee.payee_name}", "attack": True,
                    **_decision(res)})


def _combined(a):
    _r3(a, gap_minutes=15)
    _r2(a)
    a.steps.append({"label": "The card is now flagged — so the gang switches to the phished net-banking login",
                    "attack": True, "info": True})
    payee = a.add_payee(**MULE, reuse=True)
    _r9(a, amount=30000.0, payee=payee)


RUNNERS = {"R1": _r1, "R2": _r2, "R3": _r3, "R4": _r4, "R5": _r5, "R6": _r6, "R7": _r7, "R8": _r8, "R9": _r9,
           "COMBINED": _combined}


def run(fraudster, code, device, ip, city):
    code = code.upper()
    if code not in RUNNERS:
        raise AppError("Unknown attack.", "NOT_FOUND", 404)
    attack = Attack(fraudster, code, device, ip, city)
    RUNNERS[code](attack)
    decided = [s for s in attack.steps if s.get("status")]
    fired = sorted({h["rule_code"] for s in decided if s["attack"] for h in s["rules"]})
    stopped = [s for s in decided if s["attack"] and s["status"] != "APPROVED"]
    expected = SCENARIOS[code]["rules"]
    return {
        "scenario": code,
        "title": SCENARIOS[code]["title"],
        "story": SCENARIOS[code]["story"],
        "victim": {"name": attack.victim["name"], "username": attack.victim["username"],
                   "home_city": attack.victim["home_city"]},
        "from": {"city": attack.city, "device": attack.device},
        "expected_rules": expected,
        "rules_fired": fired,
        "expected_rules_fired": all(r in fired for r in expected),
        "bank_decision": stopped[-1]["status"] if stopped else ("APPROVED" if decided else "REFUSED"),
        "steps": attack.steps,
    }


def recent(fraudster_id, limit=30):
    """This fraudster's attack payments, with the bank's decision, where the
    money is, and how the victim answered."""
    return fetch_all(
        """
        SELECT ae.id, ae.scenario, ae.step, ae.created_at, t.id AS txn_id, t.external_ref, t.amount, t.status,
               t.funds_status, t.risk_score, c.name AS victim,
               (SELECT GROUP_CONCAT(rh.rule_code ORDER BY rh.rule_code) FROM rule_hits rh WHERE rh.txn_id = t.id) AS rules,
               (SELECT ca.action_status FROM customer_alerts ca WHERE ca.txn_id = t.id AND ca.severity <> 'INFO'
                 ORDER BY ca.id LIMIT 1) AS customer_response
          FROM attack_events ae
          JOIN transactions t ON t.id = ae.txn_id
          JOIN customers c ON c.id = ae.customer_id
         WHERE ae.fraudster_id = :f
         ORDER BY ae.id DESC LIMIT :lim
        """, {"f": fraudster_id, "lim": limit})
