"""OTP Shield endpoints used by the demo bank app (both phones)."""

from flask import Blueprint, g, request

from portal.extensions import db, limiter
from portal.helpers.auth_helpers import bank_session_required
from portal.helpers.responses import AppError, ok
from portal.helpers.validators import ApprovalResponseSchema, OtpRequestSchema, OtpVerifySchema, load
from portal.models import DeviceApproval, Notification, OtpRequest
from portal.services import otp_shield

otp_bp = Blueprint("otp", __name__)


@otp_bp.post("/otp/request")
@limiter.limit("30 per 10 minutes")
@bank_session_required
def request_otp():
    data = load(OtpRequestSchema, request.get_json(silent=True))
    result = otp_shield.request_otp(
        g.bank["account_id"], data["beneficiary_id"], data["amount"],
        g.bank["device_id"], g.bank["ip_address"], g.bank["city"],
    )
    return ok(result, 201)


@otp_bp.post("/otp/verify")
@limiter.limit("30 per 10 minutes")
@bank_session_required
def verify_otp():
    data = load(OtpVerifySchema, request.get_json(silent=True))
    result = otp_shield.verify_otp(
        data["otp_request_id"], data["otp"], g.bank["device_id"],
        account_id=g.bank["account_id"], ip_address=g.bank["ip_address"], city=g.bank["city"],
    )
    return ok(result)


@otp_bp.get("/otp/request/<int:otp_request_id>/status")
@bank_session_required
def request_status(otp_request_id):
    return ok(otp_shield.request_status(otp_request_id, account_id=g.bank["account_id"]))


@otp_bp.get("/otp/approval/pending")
@bank_session_required
def pending_approvals():
    account_id = request.args.get("account_id", type=int) or g.bank["account_id"]
    if account_id != g.bank["account_id"]:
        raise AppError("You can only see approvals for your own account.", "FORBIDDEN", 403)
    rows = (
        DeviceApproval.query.filter_by(account_id=account_id, status="PENDING")
        .order_by(DeviceApproval.created_at.desc())
        .all()
    )
    items = []
    for approval in rows:
        otp_req = db.session.get(OtpRequest, approval.otp_request_id)
        item = approval.to_dict()
        item["request"] = otp_shield.request_status(otp_req.id)
        items.append(item)
    return ok(items)


@otp_bp.post("/otp/approval/<int:approval_id>/respond")
@bank_session_required
def respond(approval_id):
    approval = db.session.get(DeviceApproval, approval_id)
    if approval is None or approval.account_id != g.bank["account_id"]:
        raise AppError("We couldn't find that approval request.", "APPROVAL_NOT_FOUND", 404)
    data = load(ApprovalResponseSchema, request.get_json(silent=True))
    return ok(otp_shield.respond_approval(approval_id, data["answer"], g.bank["device_id"]))


@otp_bp.get("/notifications")
@bank_session_required
def notifications():
    customer_id = request.args.get("customer_id", type=int) or g.bank["customer_id"]
    if customer_id != g.bank["customer_id"]:
        raise AppError("You can only see your own messages.", "FORBIDDEN", 403)
    since = request.args.get("since_id", type=int) or 0
    rows = (
        Notification.query.filter(Notification.customer_id == customer_id, Notification.id > since)
        .order_by(Notification.id.desc())
        .limit(30)
        .all()
    )
    return ok([n.to_dict() for n in rows])
