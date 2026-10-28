"""
A tiny demo "bank app" so the OTP Shield story can be played end to end:
log in (as Ravi, from any device), add a payee, send money. Demo only.
"""

from datetime import datetime, timedelta

from flask import Blueprint, g, request
from flask_jwt_extended import create_access_token

from portal.extensions import db, limiter
from portal.helpers.auth_helpers import bank_session_required, check_password, min_role
from portal.helpers.responses import AppError, ok
from portal.helpers.validators import BankLoginSchema, PayeeSchema, SendMoneySchema, load
from portal.models import Account, Beneficiary, Customer, Device, SessionEvent
from portal.seeders.seed_demo_story import DEMO_SCAM_PAYEE, RAVI, reset_story
from portal.services import otp_shield
from portal.services.simulator import ip_for_device

bank_demo_bp = Blueprint("bank_demo", __name__, url_prefix="/bank-demo")


def _profile(customer, account, device_id):
    payees = Beneficiary.query.filter_by(account_id=account.id).order_by(Beneficiary.added_at).all()
    trusted = Device.query.filter_by(account_id=account.id, device_id=device_id, is_trusted=True).first()
    return {
        "customer": {"id": customer.id, "name": customer.name, "home_city": customer.home_city},
        "account": {"id": account.id, "masked_no": "XXXX" + account.account_no[-4:],
                    "balance": float(account.balance)},
        "device": {"device_id": device_id, "is_trusted": trusted is not None},
        "payees": [p.to_dict() for p in payees],
    }


@bank_demo_bp.get("/info")
def demo_info():
    """What the demo screens need to pre-fill (public, contains no secrets
    beyond the published demo password)."""
    return ok({
        "netbanking_id": RAVI["netbanking_id"],
        "demo_password": RAVI["password"],
        "trusted_device_id": RAVI["device_id"],
        "trusted_device_label": RAVI["device_label"],
        "trusted_ip": ip_for_device(RAVI["device_id"]),
        "home_city": RAVI["home_city"],
        "scam_payee": DEMO_SCAM_PAYEE,
    })


@bank_demo_bp.post("/login")
@limiter.limit("20 per minute")
def login():
    data = load(BankLoginSchema, request.get_json(silent=True))
    customer = Customer.query.filter_by(netbanking_id=data["netbanking_id"].strip()).first()
    if customer is None or not check_password(data["password"], customer.netbanking_password_hash):
        raise AppError("Wrong user ID or password.", "INVALID_CREDENTIALS", 401)
    account = Account.query.filter_by(customer_id=customer.id).order_by(Account.id).first()
    db.session.add(SessionEvent(account_id=account.id, device_id=data["device_id"], ip_address=data["ip_address"],
                                city=data["city"], event_type="LOGIN", created_at=datetime.now()))
    db.session.commit()
    token = create_access_token(
        identity=f"bank:{customer.id}",
        expires_delta=timedelta(minutes=30),
        additional_claims={
            "kind": "bank",
            "customer_id": customer.id,
            "account_id": account.id,
            "device_id": data["device_id"],
            "ip_address": data["ip_address"],
            "city": data["city"],
        },
    )
    return ok({"token": token, **_profile(customer, account, data["device_id"])})


@bank_demo_bp.get("/me")
@bank_session_required
def me():
    customer = db.session.get(Customer, g.bank["customer_id"])
    account = db.session.get(Account, g.bank["account_id"])
    return ok(_profile(customer, account, g.bank["device_id"]))


@bank_demo_bp.post("/payees")
@bank_session_required
def add_payee():
    data = load(PayeeSchema, request.get_json(silent=True))
    payee = Beneficiary(
        account_id=g.bank["account_id"],
        payee_name=data["payee_name"].strip(),
        payee_account_no=data["payee_account_no"],
        payee_ifsc=data["payee_ifsc"],
        added_at=datetime.now(),
        added_device_id=g.bank["device_id"],
    )
    db.session.add(payee)
    db.session.commit()
    return ok(payee.to_dict(), 201)


@bank_demo_bp.post("/send")
@bank_session_required
def send_money():
    """Starts a payment: OTP Shield decides whether an OTP may be sent at all."""
    data = load(SendMoneySchema, request.get_json(silent=True))
    account = db.session.get(Account, g.bank["account_id"])
    if float(data["amount"]) > float(account.balance):
        raise AppError("Not enough balance for this payment.", "INSUFFICIENT_FUNDS", 400)
    result = otp_shield.request_otp(
        g.bank["account_id"], data["beneficiary_id"], data["amount"],
        g.bank["device_id"], g.bank["ip_address"], g.bank["city"],
    )
    return ok(result, 201)


@bank_demo_bp.post("/reset")
@min_role("ANALYST")
def reset():
    """Puts Ravi back to the start so the story can be replayed."""
    if not reset_story():
        raise AppError("The demo customer is missing. Run `flask seed`.", "NOT_SEEDED", 404)
    return ok({"reset": True})
