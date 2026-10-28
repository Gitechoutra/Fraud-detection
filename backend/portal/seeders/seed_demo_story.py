"""
Ravi -- the demo customer for the OTP Shield story.

Ravi Kumar lives in Hyderabad, uses one phone ("Ravi's Pixel 7"), spends
about ₹2,500 a time, and has two long-standing payees. His history is
deterministic so the demo always behaves the same way:

  * fraudster on a new phone in Delhi, new payee, ₹48,000
        -> OTP Shield: no OTP, "Was this you?" on Ravi's phone
  * Ravi on his own phone, new payee, ₹10,000
        -> OTP sent with a clear warning
  * Ravi on his own phone, existing payee (Amma), ₹2,000
        -> normal OTP
"""

import random
from datetime import date, datetime, timedelta

from sqlalchemy import text

from portal.extensions import db
from portal.helpers.auth_helpers import hash_password
from portal.helpers.db_helpers import fetch_all, set_actor
from portal.models import Account, Beneficiary, Customer, Device, Merchant, Transaction
from portal.services.simulator import ip_for_device

RAVI = {
    "name": "Ravi Kumar",
    "phone": "+919848022338",
    "email": "ravi.kumar@example.in",
    "home_city": "Hyderabad",
    "netbanking_id": "ravi.kumar",
    "password": "Ravi@123",
    "account_no": "30219876543210",
    "device_id": "RAVI-PIXEL-7",
    "device_label": "Ravi's Pixel 7",
    "typical": 2500,
}
RAVI_PAYEES = [
    ("Amma (Lakshmi Kumar)", "20114455667788", "SBIN0004567", 420),
    ("Suresh Reddy (House Owner)", "50100233445566", "HDFC0001234", 210),
]
# Ready-made payee shown in the demo "Add payee" form for the fraudster.
DEMO_SCAM_PAYEE = {"payee_name": "Kumar", "payee_account_no": "77001234567890", "payee_ifsc": "PUNB0123400"}


def ravi_account():
    customer = Customer.query.filter_by(netbanking_id=RAVI["netbanking_id"]).first()
    if customer is None:
        return None, None
    return customer, Account.query.filter_by(customer_id=customer.id).first()


def run(log=print):
    customer, _ = ravi_account()
    if customer is not None:
        log("  demo story (Ravi): already present")
        return
    rng = random.Random(1987)
    now = datetime.now()
    customer = Customer(
        name=RAVI["name"], phone=RAVI["phone"], email=RAVI["email"], home_city=RAVI["home_city"],
        kyc_status="VERIFIED", created_at=now - timedelta(days=2200), typical_amount=RAVI["typical"],
        active_from_hour=7, active_to_hour=22, usual_channels="UPI,CARD,NETBANKING",
        netbanking_id=RAVI["netbanking_id"], netbanking_password_hash=hash_password(RAVI["password"]),
    )
    db.session.add(customer)
    db.session.flush()
    account = Account(customer_id=customer.id, account_no=RAVI["account_no"], account_type="SAVINGS",
                      opened_on=date.today() - timedelta(days=2100), status="ACTIVE", balance=185000)
    db.session.add(account)
    db.session.flush()
    db.session.add(Device(account_id=account.id, device_id=RAVI["device_id"], device_label=RAVI["device_label"],
                          first_seen=now - timedelta(days=500), last_seen=now - timedelta(hours=3), is_trusted=True))
    for name, acc_no, ifsc, age in RAVI_PAYEES:
        db.session.add(Beneficiary(account_id=account.id, payee_name=name, payee_account_no=acc_no,
                                   payee_ifsc=ifsc, added_at=now - timedelta(days=age),
                                   added_device_id=RAVI["device_id"]))

    # 90 days of everyday spending averaging exactly ₹2,500.
    merchants = [m.id for m in Merchant.query.filter_by(city="Hyderabad").all()] or [None]
    amounts = [round(2500 * f, 2) for f in (0.4, 0.7, 1.0, 1.3, 1.6)] * 18  # mean = 2500
    rng.shuffle(amounts)
    rows = []
    for i, amount in enumerate(amounts):
        t = (now - timedelta(days=90 - i)).replace(hour=rng.randint(9, 21), minute=rng.randint(0, 59),
                                                   second=rng.randint(0, 59), microsecond=0)
        if t > now - timedelta(minutes=30):
            t = now - timedelta(hours=2)
        rows.append({
            "external_ref": f"SEED-RAVI-{i + 1}", "account_id": account.id, "merchant_id": rng.choice(merchants),
            "amount": amount, "currency": "INR", "channel": rng.choice(["UPI", "CARD"]), "city": "Hyderabad",
            "device_id": RAVI["device_id"], "ip_address": ip_for_device(RAVI["device_id"]), "txn_time": t,
            "risk_score": 0, "status": "APPROVED", "is_fraud_label": False, "source": "SEED", "created_at": t,
        })
    db.session.execute(Transaction.__table__.insert(), rows)
    account.last_txn_at = max(r["txn_time"] for r in rows)
    db.session.commit()
    log(f"  demo story (Ravi): customer, account, trusted phone, 2 payees, {len(rows)} payments")


def reset_story():
    """Puts Ravi back to the starting point so the demo can be replayed."""
    customer, account = ravi_account()
    if account is None:
        return False
    keep_payees = [p[0] for p in RAVI_PAYEES]
    otp_rows = fetch_all(
        "SELECT o.requesting_device_id, o.ip_address, b.payee_account_no FROM otp_requests o "
        "LEFT JOIN beneficiaries b ON b.id = o.beneficiary_id WHERE o.account_id = :a",
        {"a": account.id},
    )
    set_actor("demo-reset")
    for row in otp_rows:
        for entry_type, value in (("DEVICE", row["requesting_device_id"]), ("IP", row["ip_address"]),
                                  ("ACCOUNT", row["payee_account_no"])):
            if value and value != RAVI["device_id"] and value != ip_for_device(RAVI["device_id"]):
                db.session.execute(
                    text("DELETE FROM watchlist WHERE entry_type = :t AND entry_value = :v "
                         "AND added_by = 'otp-shield'"),
                    {"t": entry_type, "v": value},
                )
    params = {"a": account.id}
    db.session.execute(text("DELETE FROM transactions WHERE account_id = :a AND source <> 'SEED'"), params)
    db.session.execute(text("DELETE FROM otp_requests WHERE account_id = :a"), params)
    db.session.execute(text("DELETE FROM notifications WHERE customer_id = :c"), {"c": customer.id})
    db.session.execute(text("DELETE FROM sessions WHERE account_id = :a"), params)
    db.session.execute(
        text("DELETE FROM beneficiaries WHERE account_id = :a AND payee_name NOT IN (:p1, :p2)"),
        {"a": account.id, "p1": keep_payees[0], "p2": keep_payees[1]},
    )
    db.session.execute(text("DELETE FROM devices WHERE account_id = :a AND device_id <> :d"),
                       {"a": account.id, "d": RAVI["device_id"]})
    db.session.execute(text("UPDATE beneficiaries SET cooling_until = NULL WHERE account_id = :a"), params)
    db.session.execute(text("UPDATE accounts SET balance = 185000, status = 'ACTIVE' WHERE id = :a"), params)
    db.session.commit()
    set_actor(None)
    return True
