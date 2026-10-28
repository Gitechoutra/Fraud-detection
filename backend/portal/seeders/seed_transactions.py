"""
90 days of normal payment history (~25,000 rows, bulk-inserted), plus a
set of labelled fraud stories run through the real engine at past dates so
the dashboard, alert queue and rule-precision view have something to show.

History rows are inserted directly as APPROVED: they represent the past
before FraudShield, and evaluating 25,000 rows one by one would only slow
setup down. Everything from now on goes through sp_evaluate_transaction.
"""

import random
from datetime import datetime, timedelta

from sqlalchemy import text

from portal.extensions import db
from portal.helpers.db_helpers import fetch_all, scalar, set_actor
from portal.models import Merchant, Transaction
from portal.services import simulator

HISTORY_DAYS = 90
CHUNK = 2000


def _history_rows(rng, days, rate_scale):
    rows = []
    accounts = fetch_all(
        """
        SELECT a.id, a.status, a.last_txn_at, c.home_city, c.typical_amount, c.active_from_hour,
               c.active_to_hour, c.usual_channels,
               (SELECT GROUP_CONCAT(d.device_id) FROM devices d
                 WHERE d.account_id = a.id AND d.is_trusted = 1) AS devices
          FROM accounts a JOIN customers c ON c.id = a.customer_id
         WHERE c.netbanking_id IS NULL
        """
    )
    merchants = Merchant.query.filter(Merchant.risk_level != "HIGH").all()
    by_city = {}
    for m in merchants:
        by_city.setdefault(m.city, []).append(m.id)
    all_ids = [m.id for m in merchants]
    now = datetime.now()
    n = 0
    for acc in accounts:
        devices = (acc["devices"] or f"DEV-X-{acc['id']}").split(",")
        channels = acc["usual_channels"].split(",")
        typical = float(acc["typical_amount"])
        lo, hi = acc["active_from_hour"], max(acc["active_from_hour"] + 1, acc["active_to_hour"])
        if acc["status"] == "DORMANT":
            # A handful of old payments before the account went quiet.
            last = acc["last_txn_at"]
            dates = [last - timedelta(days=rng.randint(0, 120)) for _ in range(rng.randint(3, 6))] + [last]
        else:
            per_day = rng.uniform(0.6, 1.7) * rate_scale
            dates = []
            for d in range(days, -1, -1):
                for _ in range(int(per_day) + (1 if rng.random() < per_day % 1 else 0)):
                    dates.append(now - timedelta(days=d))
        for day in dates:
            t = day.replace(hour=rng.randint(lo, hi - 1), minute=rng.randint(0, 59),
                            second=rng.randint(0, 59), microsecond=rng.randint(0, 999) * 1000)
            if t > now - timedelta(minutes=5):
                continue
            channel = rng.choice(channels)
            away = rng.random() < 0.04 and t < now - timedelta(days=2)
            city = rng.choice(simulator.CITIES) if away else acc["home_city"]
            device = rng.choice(devices)
            factor = min(2.5, max(0.15, rng.lognormvariate(-0.1, 0.45)))
            n += 1
            rows.append({
                "external_ref": f"SEED-{acc['id']}-{n}",
                "account_id": acc["id"],
                "merchant_id": None if channel == "ATM" else rng.choice(by_city.get(city) or all_ids),
                "amount": round(max(20.0, typical * factor), 2),
                "currency": "INR",
                "channel": channel,
                "city": city,
                "device_id": device,
                "ip_address": simulator.ip_for_device(device),
                "txn_time": t,
                "risk_score": 0,
                "status": "APPROVED",
                "is_fraud_label": False,
                "source": "SEED",
                "created_at": t,
            })
    return rows


def _labelled_frauds(rng, log, per_rule):
    """Runs the fraud stories at past dates, then closes most of their cases
    the way an analyst would, so v_rule_precision has real numbers."""
    simulator.get_cache(force=True)
    now = datetime.now()
    targets, genuine = [], []
    for code in simulator.RULE_CODES:
        for _ in range(per_rule):
            base = now - timedelta(days=rng.uniform(0.2, 85))
            ctx = simulator.ScenarioContext(source="SEED", base_time=base, live=False,
                                            rng=random.Random(rng.random()), prefix="SEEDF")
            try:
                simulator.SCENARIOS[code](ctx)
            except Exception as exc:
                db.session.rollback()
                log(f"    scenario {code} skipped: {exc}")
                continue
            targets += [r["result"] for r in ctx.results if r["label"] == 1]
    # Genuine payments that look risky (a real late-night hospital bill, a
    # real big purchase): flagged, then cleared by an analyst.
    for code in ("R5", "R1", "R4"):
        for _ in range(max(1, per_rule // 2)):
            ctx = simulator.ScenarioContext(source="SEED", base_time=now - timedelta(days=rng.uniform(1, 80)),
                                            live=False, rng=random.Random(rng.random()), prefix="SEEDG")
            try:
                simulator.SCENARIOS[code](ctx)
            except Exception:
                db.session.rollback()
                continue
            for r in ctx.results:
                db.session.execute(
                    text("UPDATE transactions SET is_fraud_label = 0, scenario = 'GENUINE' WHERE id = :id"),
                    {"id": r["result"]["txn_id"]},
                )
                genuine.append(r["result"])
    db.session.commit()

    analyst_id = scalar("SELECT u.id FROM users u JOIN roles r ON r.id = u.role_id WHERE r.name = 'ANALYST' LIMIT 1")
    set_actor("analyst")
    closed = 0
    recent_cutoff = now - timedelta(days=3)
    for res, outcome in [(t, "CONFIRMED_FRAUD") for t in targets] + [(g, "FALSE_POSITIVE") for g in genuine]:
        row = fetch_all(
            "SELECT ca.id AS case_id, al.id AS alert_id, t.txn_time FROM transactions t "
            "JOIN alerts al ON al.txn_id = t.id JOIN cases ca ON ca.alert_id = al.id WHERE t.id = :id",
            {"id": res["txn_id"]},
        )
        if not row or row[0]["txn_time"] > recent_cutoff:
            continue  # recent ones stay open for the analyst demo
        note = ("Customer confirmed they did not make this payment." if outcome == "CONFIRMED_FRAUD"
                else "Customer confirmed the payment was genuine.")
        db.session.execute(
            text("UPDATE cases SET outcome = :o, analyst_id = :a, notes = :n, closed_at = :c WHERE id = :id"),
            {"o": outcome, "a": analyst_id, "n": note, "c": row[0]["txn_time"] + timedelta(hours=2),
             "id": row[0]["case_id"]},
        )
        db.session.execute(
            text("UPDATE alerts SET alert_status = 'CLOSED', assigned_to = :a WHERE id = :id"),
            {"a": analyst_id, "id": row[0]["alert_id"]},
        )
        closed += 1
    db.session.commit()
    set_actor(None)
    log(f"    labelled fraud stories: {len(targets)} targets, {len(genuine)} genuine look-alikes, {closed} cases closed")


def run(log=print, days=HISTORY_DAYS, rate_scale=1.0, frauds_per_rule=5, rng=None):
    if scalar("SELECT COUNT(*) FROM transactions WHERE source = 'SEED' AND external_ref NOT LIKE 'SEED-RAVI-%'"):
        log("  transactions: already present")
        return
    rng = rng or random.Random(2024)
    rows = _history_rows(rng, days, rate_scale)
    table = Transaction.__table__
    for i in range(0, len(rows), CHUNK):
        db.session.execute(table.insert(), rows[i:i + CHUNK])
    db.session.execute(text(
        "UPDATE accounts a JOIN (SELECT account_id, MAX(txn_time) AS last_t FROM transactions "
        "GROUP BY account_id) x ON x.account_id = a.id "
        "SET a.last_txn_at = x.last_t WHERE a.status = 'ACTIVE'"
    ))
    db.session.commit()
    log(f"  transactions: {len(rows)} history rows inserted")
    if frauds_per_rule:
        _labelled_frauds(rng, log, frauds_per_rule)
