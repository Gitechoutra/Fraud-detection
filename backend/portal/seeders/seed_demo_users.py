"""
Demo logins for the customer banking app (/bank) and the fraudster
simulation console (/attacker).

Customers (password Name@123, e.g. Ravi@123):
  ravi     Ravi Kumar, Hyderabad   -- the existing OTP Shield demo customer
  priya    Priya Sharma, Bengaluru -- a high spender
  suresh   Suresh Babu, Chennai
  lakshmi  Lakshmi Kumar, Hyderabad -- DORMANT: last activity ~7 months ago
  arjun    Arjun Mehta, Pune
Each has a trusted phone, a card (a known, untrusted "CARD-nnnn" device),
two long-standing payees and 90 days of everyday payments (Lakshmi's 90
days ended seven months ago), so the nine rules have real history to use.

Fraudsters (password Hacker@123): hacker1 "Delhi Gang", hacker2 "Mumbai
Crew", each holding stolen credentials for four of the customers. The gang's
mule account is on the watchlist.

run() only adds what is missing -- it never changes an existing customer,
balance or payment. reset_demo() puts the five demo accounts back to their
seeded state between demos.
"""

import random
from datetime import date, datetime, timedelta

from sqlalchemy import bindparam, text

from portal.extensions import db
from portal.helpers.auth_helpers import hash_password
from portal.helpers.db_helpers import fetch_all, scalar, set_actor
from portal.models import (
    Account,
    Beneficiary,
    Customer,
    CustomerUser,
    Device,
    FraudsterUser,
    Merchant,
    StolenCredential,
    Transaction,
)
from portal.seeders import seed_demo_story
from portal.services.attacker import MULE
from portal.services.simulator import ip_for_device

CUSTOMERS = [
    {"username": "ravi", "name": "Ravi Kumar", "card": "4417"},  # created by seed_demo_story
    {"username": "priya", "name": "Priya Sharma", "phone": "+919845012345", "home_city": "Bengaluru",
     "account_no": "30219876543301", "balance": 420000, "typical": 8000, "device": "PRIYA-IPHONE-14",
     "device_label": "Priya's iPhone 14", "card": "5521",
     "payees": [("Ananya Sharma (Sister)", "20114455661122", "SBIN0001122", 380),
                ("Prestige Apartments Maintenance", "50100233441199", "HDFC0004411", 300)]},
    {"username": "suresh", "name": "Suresh Babu", "phone": "+919840098765", "home_city": "Chennai",
     "account_no": "30219876543402", "balance": 95000, "typical": 2000, "device": "SURESH-GALAXY-A54",
     "device_label": "Suresh's Galaxy A54", "card": "7302",
     "payees": [("Meena Babu (Wife)", "20114455662233", "IOBA0002233", 900),
                ("Chennai Corporation Tax", "50100233442288", "CNRB0002288", 700)]},
    {"username": "lakshmi", "name": "Lakshmi Kumar", "phone": "+919848033221", "home_city": "Hyderabad",
     "account_no": "30219876543503", "balance": 260000, "typical": 3000, "device": "LAKSHMI-REDMI-NOTE",
     "device_label": "Lakshmi's Redmi Note", "card": "1189", "dormant": True,
     "payees": [("Ravi Kumar (Son)", "30219876543210", "SBIN0004567", 1500),
                ("Apollo Pharmacy", "50100233443377", "ICIC0003377", 800)]},
    {"username": "arjun", "name": "Arjun Mehta", "phone": "+919822011223", "home_city": "Pune",
     "account_no": "30219876543604", "balance": 60000, "typical": 1800, "device": "ARJUN-ONEPLUS-11",
     "device_label": "Arjun's OnePlus 11", "card": "6650",
     "payees": [("Rohan Mehta (Brother)", "20114455664455", "KKBK0004455", 600),
                ("Hostel Mess Pune", "50100233444466", "MAHB0004466", 400)]},
]
FRAUDSTERS = [
    {"username": "hacker1", "display_name": "Delhi Gang", "base_city": "Delhi",
     "stolen": [("ravi", "PHISHING_LINK"), ("suresh", "CARD_SKIMMING"), ("lakshmi", "SIM_SWAP"), ("priya", "OTP_CALL")]},
    {"username": "hacker2", "display_name": "Mumbai Crew", "base_city": "Mumbai",
     "stolen": [("arjun", "CARD_SKIMMING"), ("priya", "PHISHING_LINK"), ("lakshmi", "OTP_CALL"), ("suresh", "SIM_SWAP")]},
]
DORMANT_DAYS = 210


def demo_password(username):
    return f"{username.capitalize()}@123"


FRAUDSTER_PASSWORD = "Hacker@123"


def _history(account, spec, end, rng, merchants, payees):
    """90 days of everyday payments ending at `end`, averaging spec['typical']."""
    factors = [0.4, 0.7, 1.0, 1.3, 1.6] * 18  # mean exactly 1.0
    rng.shuffle(factors)
    rows = []
    for i, f in enumerate(factors):
        t = (end - timedelta(days=90 - i)).replace(hour=rng.randint(9, 21), minute=rng.randint(0, 59),
                                                   second=rng.randint(0, 59), microsecond=0)
        card = i % 3 == 0
        to_payee = not card and i % 15 == 7
        device = f"CARD-{spec['card']}" if card else spec["device"]
        rows.append({
            "external_ref": f"SEED-{spec['username'].upper()}-{i + 1}", "account_id": account.id,
            "merchant_id": None if to_payee else rng.choice(merchants),
            "beneficiary_id": rng.choice(payees).id if to_payee else None,
            "amount": round(spec["typical"] * f, 2), "currency": "INR",
            "channel": "CARD" if card else rng.choice(["UPI", "NETBANKING"]) if to_payee else "UPI",
            "city": spec["home_city"], "device_id": device, "ip_address": ip_for_device(spec["device"]),
            "txn_time": min(t, end), "risk_score": 0, "status": "APPROVED", "is_fraud_label": False,
            "source": "SEED", "created_at": min(t, end),
        })
    db.session.execute(Transaction.__table__.insert(), rows)
    return max(r["txn_time"] for r in rows)


def _create_customer(spec, now, rng):
    end = now - timedelta(days=DORMANT_DAYS) if spec.get("dormant") else now - timedelta(hours=3)
    customer = Customer(name=spec["name"], phone=spec["phone"], home_city=spec["home_city"], kyc_status="VERIFIED",
                        created_at=now - timedelta(days=2000), typical_amount=spec["typical"], active_from_hour=7,
                        active_to_hour=22, usual_channels="UPI,CARD,NETBANKING")
    db.session.add(customer)
    db.session.flush()
    account = Account(customer_id=customer.id, account_no=spec["account_no"], account_type="SAVINGS",
                      opened_on=date.today() - timedelta(days=1900), status="DORMANT" if spec.get("dormant") else "ACTIVE",
                      balance=spec["balance"], held_amount=0)
    db.session.add(account)
    db.session.flush()
    db.session.add(Device(account_id=account.id, device_id=spec["device"], device_label=spec["device_label"],
                          first_seen=end - timedelta(days=400), last_seen=end, is_trusted=True))
    payees = []
    for name, acc_no, ifsc, age in spec["payees"]:
        p = Beneficiary(account_id=account.id, payee_name=name, payee_account_no=acc_no, payee_ifsc=ifsc,
                        added_at=now - timedelta(days=age), added_device_id=spec["device"])
        db.session.add(p)
        payees.append(p)
    db.session.flush()
    merchants = [m.id for m in Merchant.query.filter_by(city=spec["home_city"]).all()] or [None]
    account.last_txn_at = _history(account, spec, end, rng, merchants, payees)
    return customer, account


def _card_device(account, card, now):
    if not Device.query.filter_by(account_id=account.id, device_id=f"CARD-{card}").first():
        db.session.add(Device(account_id=account.id, device_id=f"CARD-{card}", device_label=f"Debit card ending {card}",
                              first_seen=now - timedelta(days=700), last_seen=now - timedelta(days=1), is_trusted=False))


def run(log=print):
    seed_demo_story.run(log)  # Ravi
    rng = random.Random(2024)
    now = datetime.now()
    added = []
    for spec in CUSTOMERS:
        if CustomerUser.query.filter_by(username=spec["username"]).first():
            continue
        if spec["username"] == "ravi":
            customer, account = seed_demo_story.ravi_account()
        else:
            customer = Customer.query.join(Account).filter(Account.account_no == spec["account_no"]).first()
            account = customer and Account.query.filter_by(customer_id=customer.id).first()
            if customer is None:
                customer, account = _create_customer(spec, now, rng)
        _card_device(account, spec["card"], now)
        db.session.add(CustomerUser(customer_id=customer.id, username=spec["username"],
                                    password_hash=hash_password(demo_password(spec["username"])), card_last4=spec["card"]))
        added.append(spec["username"])
    for spec in FRAUDSTERS:
        user = FraudsterUser.query.filter_by(username=spec["username"]).first()
        if user is None:
            user = FraudsterUser(username=spec["username"], password_hash=hash_password(FRAUDSTER_PASSWORD),
                                 display_name=spec["display_name"], base_city=spec["base_city"])
            db.session.add(user)
            db.session.flush()
            added.append(spec["username"])
        for username, how in spec["stolen"]:
            cu = CustomerUser.query.filter_by(username=username).first()
            if cu and not StolenCredential.query.filter_by(fraudster_id=user.id, customer_id=cu.customer_id).first():
                db.session.add(StolenCredential(fraudster_id=user.id, customer_id=cu.customer_id, obtained_via=how,
                                                obtained_at=now - timedelta(days=rng.randint(1, 6))))
    set_actor("seed")
    db.session.execute(
        text("INSERT IGNORE INTO watchlist (entry_type, entry_value, reason, added_by, added_at) "
             "VALUES ('ACCOUNT', :v, 'Mule account collecting scam money (demo gang)', 'seed', NOW(3))"),
        {"v": MULE["payee_account_no"]})
    db.session.commit()
    set_actor(None)
    log(f"  demo logins: {', '.join(added) if added else 'already present'}")


# --------------------------------------------------------------------------
# Reset between demos
# --------------------------------------------------------------------------


def _demo_accounts():
    rows = fetch_all(
        "SELECT cu.username, c.id AS customer_id, a.id AS account_id FROM customer_users cu "
        "JOIN customers c ON c.id = cu.customer_id JOIN accounts a ON a.customer_id = c.id")
    return {r["username"]: r for r in rows if r["username"] in {c["username"] for c in CUSTOMERS}}


def reset_demo():
    """Removes everything that happened to the demo accounts since seeding
    (payments, alerts, cases, holds, logins, OTPs, added payees and devices,
    and the watchlist entries those payments created) and restores their
    balances. Seeded history and other customers are untouched."""
    accounts = _demo_accounts()
    if not accounts:
        return {"reset": [], "message": "No demo customers yet. Run `flask seed-demo`."}
    specs = {c["username"]: c for c in CUSTOMERS}
    ids = [a["account_id"] for a in accounts.values()]
    marks = ", ".join(f":a{i}" for i in range(len(ids)))
    params = {f"a{i}": v for i, v in enumerate(ids)}
    txn_ids = [r["id"] for r in fetch_all(
        f"SELECT id FROM transactions WHERE account_id IN ({marks}) AND source <> 'SEED'", params)]
    set_actor("demo-reset")
    # Watchlist entries created by these payments (reports, R9 follow-up, OTP Shield NO answers).
    for txn_id in txn_ids:
        db.session.execute(text("DELETE FROM watchlist WHERE added_by IN ('customer-report', 'r9-engine') "
                                "AND reason LIKE :r"), {"r": f"%payment #{txn_id}%"})
    for row in fetch_all(
        f"SELECT o.requesting_device_id, o.ip_address FROM otp_requests o WHERE o.account_id IN ({marks})", params):
        for entry_type, value in (("DEVICE", row["requesting_device_id"]), ("IP", row["ip_address"])):
            db.session.execute(text("DELETE FROM watchlist WHERE added_by = 'otp-shield' AND entry_type = :t "
                                    "AND entry_value = :v"), {"t": entry_type, "v": value})
    db.session.execute(text(f"DELETE FROM transactions WHERE account_id IN ({marks}) AND source <> 'SEED'"), params)
    db.session.execute(text(f"DELETE FROM otp_requests WHERE account_id IN ({marks})"), params)
    db.session.execute(text(f"DELETE FROM sessions WHERE account_id IN ({marks})"), params)
    customer_marks = ", ".join(f":c{i}" for i in range(len(accounts)))
    cparams = {f"c{i}": a["customer_id"] for i, a in enumerate(accounts.values())}
    db.session.execute(text(f"DELETE FROM customer_alerts WHERE customer_id IN ({customer_marks})"), cparams)
    db.session.execute(text(f"DELETE FROM notifications WHERE customer_id IN ({customer_marks})"), cparams)
    db.session.execute(text(f"UPDATE customer_users SET is_locked = 0, failed_logins = 0 "
                            f"WHERE customer_id IN ({customer_marks})"), cparams)
    for username, acc in accounts.items():
        spec = specs[username]
        keep_payees = [p[0] for p in (spec.get("payees") or seed_demo_story.RAVI_PAYEES)]
        keep_device = spec.get("device") or seed_demo_story.RAVI["device_id"]
        a = {"a": acc["account_id"]}
        db.session.execute(text("DELETE FROM beneficiaries WHERE account_id = :a AND payee_name NOT IN :keep")
                           .bindparams(bindparam("keep", expanding=True)), {**a, "keep": keep_payees})
        db.session.execute(text("UPDATE beneficiaries SET cooling_until = NULL WHERE account_id = :a"), a)
        db.session.execute(text("DELETE FROM devices WHERE account_id = :a AND device_id NOT IN (:d, :card)"),
                           {**a, "d": keep_device, "card": f"CARD-{spec['card']}"})
        balance = spec.get("balance", 185000)
        last = scalar("SELECT MAX(txn_time) FROM transactions WHERE account_id = :a AND status = 'APPROVED'", a)
        db.session.execute(
            text("UPDATE accounts SET held_amount = 0, balance = :b, status = :s, last_txn_at = :l, step_up_until = NULL "
                 "WHERE id = :a"),
            {**a, "b": balance, "s": "DORMANT" if spec.get("dormant") else "ACTIVE", "l": last})
    db.session.commit()
    set_actor(None)
    return {"reset": sorted(accounts), "payments_removed": len(txn_ids)}
