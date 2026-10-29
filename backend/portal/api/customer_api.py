"""
Customer banking app (/bank): login, balance, payees, payments, history and
fraud alerts with "This was me" / "Not me".

Every endpoint works only on the logged-in customer's own account: the
customer and account ids come from the token (g.customer), never from the
request. Payments go through fraud_engine.ingest like every other payment,
so sp_evaluate_transaction makes the decision and services/funds moves (or
holds) the money.
"""

from datetime import datetime

from flask import Blueprint, g, request
from flask_jwt_extended import get_jwt

from portal.api.auth_api import _revoke
from portal.extensions import db, limiter
from portal.helpers.auth_helpers import check_password, customer_required
from portal.helpers.db_helpers import execute, fetch_all, jsonable, scalar
from portal.helpers.demo_context import demo_city, device_id, issue_token, network_address
from portal.helpers.responses import AppError, ok, page_args
from portal.helpers.validators import (
    CUSTOMER_DAILY_MAX,
    ConfirmAlertSchema,
    CustomerPaymentSchema,
    DemoLoginSchema,
    load,
)
from portal.models import Account, Beneficiary, Customer, CustomerUser, Device, SessionEvent
from portal.services import customer_care, fraud_engine

customer_bp = Blueprint("customer", __name__, url_prefix="/customer")

MAX_FAILED_LOGINS = 5


def _profile(customer_user, device):
    customer = db.session.get(Customer, customer_user.customer_id)
    account = Account.query.filter_by(customer_id=customer.id).order_by(Account.id).first()
    trusted = Device.query.filter_by(account_id=account.id, device_id=device, is_trusted=True).first() is not None
    return {
        "username": customer_user.username,
        "customer": {"name": customer.name, "home_city": customer.home_city, "phone": "XXXXXX" + customer.phone[-4:]},
        "account": {
            "masked_no": "XXXX" + account.account_no[-4:],
            "status": account.status,
            "balance": float(account.balance),
            "held_amount": float(account.held_amount or 0),
            "available": float(account.balance - (account.held_amount or 0)),
        },
        "card": {"last4": customer_user.card_last4},
        "device": {"device_id": device, "is_trusted": trusted, "city": demo_city(customer.home_city)},
        "unread_alerts": scalar(
            "SELECT COUNT(*) FROM customer_alerts WHERE customer_id = :c AND read_at IS NULL", {"c": customer.id}),
    }


@customer_bp.post("/login")
@limiter.limit("10 per minute")
def login():
    data = load(DemoLoginSchema, request.get_json(silent=True))
    device = device_id()
    cu = CustomerUser.query.filter_by(username=data["username"]).first()
    if cu is not None and cu.is_locked:
        raise AppError("This login is locked after too many wrong passwords. Please call the bank.", "ACCOUNT_LOCKED", 423)
    if cu is None or not check_password(data["password"], cu.password_hash):
        if cu is not None:
            cu.failed_logins += 1
            cu.is_locked = cu.failed_logins >= MAX_FAILED_LOGINS
            db.session.commit()
        raise AppError("Wrong username or password.", "INVALID_CREDENTIALS", 401)
    customer = db.session.get(Customer, cu.customer_id)
    account = Account.query.filter_by(customer_id=cu.customer_id).order_by(Account.id).first()
    cu.failed_logins, cu.last_login_at = 0, datetime.now()
    # A login is a security event the fraud rules look at (R9, OTP Shield).
    db.session.add(SessionEvent(account_id=account.id, device_id=device, ip_address=network_address(device),
                                city=demo_city(customer.home_city), event_type="LOGIN", created_at=datetime.now()))
    db.session.commit()
    token = issue_token("customer", cu.id, account_id=account.id)
    return ok({"token": token, **_profile(cu, device)})


@customer_bp.post("/logout")
@customer_required
def logout():
    _revoke(get_jwt()["jti"], "access")
    db.session.commit()
    return ok({"logged_out": True})


@customer_bp.get("/me")
@customer_required
def me():
    return ok(_profile(db.session.get(CustomerUser, g.customer["user_id"]), device_id()))


@customer_bp.get("/payees")
@customer_required
def payees():
    rows = Beneficiary.query.filter_by(account_id=g.customer["account_id"]).order_by(Beneficiary.added_at).all()
    return ok([{"id": p.id, "payee_name": p.payee_name, "masked_account": "XXXX" + p.payee_account_no[-4:],
                "added_at": p.added_at.isoformat(), "on_hold_until": p.cooling_until.isoformat() if p.cooling_until else None}
               for p in rows])


@customer_bp.post("/payments")
@limiter.limit("20 per minute")
@customer_required
def pay():
    data = load(CustomerPaymentSchema, request.get_json(silent=True))
    account_id = g.customer["account_id"]
    payee = db.session.get(Beneficiary, data["beneficiary_id"])
    if payee is None or payee.account_id != account_id:
        raise AppError("That payee is not on your list.", "PAYEE_NOT_FOUND", 404)
    now = datetime.now()
    if payee.cooling_until and payee.cooling_until > now:
        raise AppError(f"Payments to {payee.payee_name} are on a safety hold until "
                       f"{payee.cooling_until:%d %b %H:%M}.", "PAYEE_ON_HOLD", 423)
    external_ref = f"APP-{account_id}-{data['idempotency_key']}"
    existing = fraud_engine.existing_decision(external_ref)
    if existing:  # a retried request: same decision, no second payment
        return ok(existing)
    today = scalar(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE account_id = :a AND source = 'CUSTOMER_APP' "
        "AND txn_time >= CURDATE() AND status IN ('APPROVED', 'REVIEW')", {"a": account_id})
    if float(today) + float(data["amount"]) > CUSTOMER_DAILY_MAX:
        raise AppError("This would go over your daily limit of ₹5,00,000.", "DAILY_LIMIT", 422)
    account = db.session.get(Account, account_id)
    if float(data["amount"]) > float(account.balance - (account.held_amount or 0)):
        raise AppError("Not enough available balance for this payment.", "INSUFFICIENT_FUNDS", 422)
    device = device_id()
    customer = db.session.get(Customer, g.customer["customer_id"])
    result = fraud_engine.ingest({
        "external_ref": external_ref,
        "account_id": account_id,
        "beneficiary_id": payee.id,
        "amount": data["amount"],
        "channel": data["channel"],
        "city": demo_city(customer.home_city),
        "device_id": device,
        "ip_address": network_address(device),
        "txn_time": now,
        "source": "CUSTOMER_APP",
    }, source="CUSTOMER_APP")
    return ok(result, 201)


@customer_bp.get("/transactions")
@customer_required
def history():
    page, per_page, offset = page_args(20)
    params = {"a": g.customer["account_id"], "lim": per_page, "off": offset}
    total = scalar("SELECT COUNT(*) FROM transactions WHERE account_id = :a", params)
    rows = fetch_all(
        """
        SELECT t.id, t.external_ref, t.txn_time, t.amount, t.channel, t.city, t.status, t.funds_status,
               COALESCE(b.payee_name, m.name) AS counterparty,
               (SELECT GROUP_CONCAT(rh.rule_code ORDER BY rh.rule_code) FROM rule_hits rh WHERE rh.txn_id = t.id) AS rules
          FROM transactions t
          LEFT JOIN beneficiaries b ON b.id = t.beneficiary_id
          LEFT JOIN merchants m ON m.id = t.merchant_id
         WHERE t.account_id = :a
         ORDER BY t.txn_time DESC, t.id DESC LIMIT :lim OFFSET :off
        """, params)
    return ok({"items": [jsonable(r) for r in rows], "total": total, "page": page, "per_page": per_page,
               "pages": max(1, -(-total // per_page))})


@customer_bp.get("/alerts")
@customer_required
def alerts():
    since = max(0, request.args.get("since_id", 0, type=int))
    rows = customer_care.alerts_for(g.customer["customer_id"], since)
    unread = scalar("SELECT COUNT(*) FROM customer_alerts WHERE customer_id = :c AND read_at IS NULL",
                    {"c": g.customer["customer_id"]})
    return ok({"items": [jsonable(r) for r in rows], "unread": unread, "server_time": datetime.now().isoformat()})


@customer_bp.post("/alerts/read")
@customer_required
def mark_read():
    execute("UPDATE customer_alerts SET read_at = NOW(3) WHERE customer_id = :c AND read_at IS NULL",
            {"c": g.customer["customer_id"]})
    db.session.commit()
    return ok({"unread": 0})


@customer_bp.post("/alerts/<int:alert_id>/confirm")
@limiter.limit("10 per minute")
@customer_required
def confirm(alert_id):
    data = load(ConfirmAlertSchema, request.get_json(silent=True))
    return ok(customer_care.confirm(g.customer["user_id"], g.customer["customer_id"], alert_id, data["password"],
                                   device_id()))


@customer_bp.post("/alerts/<int:alert_id>/report")
@customer_required
def report(alert_id):
    return ok(customer_care.report_not_me(g.customer["user_id"], g.customer["customer_id"], alert_id))
