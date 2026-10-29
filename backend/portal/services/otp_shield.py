"""
portal/services/otp_shield.py
=============================
OTP Shield -- checkpoint R9-A, *before* any OTP exists.

request_otp()      asks sp_otp_risk_check who is asking, then either sends a
                   normal OTP, sends an OTP that spells out exactly what it
                   is for, or sends NO OTP and asks the customer's registered
                   phone "Was this you?" instead.
verify_otp()       checks the OTP (3 attempts, 3-minute expiry, stored only
                   as a hash) and then runs the payment through the normal
                   fraud engine, where rule R9 is the second safety net.
respond_approval() handles the customer's YES / NO.
"""

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta

from flask import current_app
from sqlalchemy import text

from portal.extensions import db
from portal.helpers.db_helpers import call_procedure, set_actor
from portal.helpers.explain import inr
from portal.helpers.responses import AppError
from portal.models import (
    Account,
    Alert,
    Beneficiary,
    Case,
    Device,
    DeviceApproval,
    OtpRequest,
    SessionEvent,
    Transaction,
)
from portal.services import fraud_engine
from portal.services.notifier import get_notifier

REQUESTER_MESSAGES = {
    "OTP_SENT": "We sent an OTP to your registered mobile number.",
    "OTP_SENT_WITH_WARNING": (
        "We sent an OTP to your registered mobile number. Please read the message carefully "
        "before using it."
    ),
    "OTP_BLOCKED_APPROVAL_REQUIRED": "Approve this payment in the app on your registered phone.",
}


def _hash_otp(otp_request_id, otp):
    key = current_app.config["SECRET_KEY"].encode("utf-8")
    return hmac.new(key, f"{otp_request_id}:{otp}".encode("utf-8"), hashlib.sha256).hexdigest()


def _json(value):
    if value is None:
        return []
    return json.loads(value) if isinstance(value, (str, bytes)) else value


def _is_trusted(account_id, device_id):
    return (
        Device.query.filter_by(account_id=account_id, device_id=device_id, is_trusted=True).first()
        is not None
    )


def _log_session(account_id, event, device_id, ip, city, at=None):
    db.session.add(
        SessionEvent(
            account_id=account_id,
            device_id=device_id,
            ip_address=ip,
            city=city,
            event_type=event,
            created_at=at or datetime.now(),
        )
    )


def request_otp(account_id, beneficiary_id, amount, device_id, ip_address=None, city=None, at=None):
    cfg = current_app.config
    at = at or datetime.now()
    account = db.session.get(Account, account_id)
    if account is None:
        raise AppError("That account does not exist.", "ACCOUNT_NOT_FOUND", 404)
    payee = db.session.get(Beneficiary, beneficiary_id)
    if payee is None or payee.account_id != account_id:
        raise AppError("That payee does not belong to this account.", "PAYEE_NOT_FOUND", 404)
    if payee.cooling_until and payee.cooling_until > at:
        raise AppError(
            f"Payments to {payee.payee_name} are on a 24-hour safety hold after a blocked attempt.",
            "PAYEE_ON_HOLD",
            423,
        )

    window_start = at - timedelta(minutes=cfg["OTP_REQUEST_WINDOW_MINUTES"])
    recent = (
        OtpRequest.query.filter(OtpRequest.account_id == account_id, OtpRequest.created_at >= window_start).count()
    )
    if recent >= cfg["OTP_MAX_REQUESTS_PER_WINDOW"]:
        raise AppError(
            "Too many OTP requests. Please wait 10 minutes and try again.", "OTP_RATE_LIMITED", 429
        )

    check = call_procedure(
        "sp_otp_risk_check", (account_id, beneficiary_id, amount, device_id, ip_address, city, at)
    )[0]
    decision = check["decision"]
    signals = _json(check["signals"])

    otp_req = OtpRequest(
        account_id=account_id,
        beneficiary_id=beneficiary_id,
        amount=amount,
        requesting_device_id=device_id,
        ip_address=ip_address,
        city=city,
        risk_points=int(check["risk_points"]),
        signals_json=signals,
        decision=decision,
        final_status="PENDING",
        created_at=at,
    )
    db.session.add(otp_req)
    db.session.flush()
    _log_session(account_id, "OTP_REQUEST", device_id, ip_address, city, at)

    notifier = get_notifier()
    approval = None
    amount_txt = inr(amount)
    if decision == "OTP_BLOCKED_APPROVAL_REQUIRED":
        # No OTP is generated at all -- there is nothing a scammer can ask for.
        approval = DeviceApproval(
            otp_request_id=otp_req.id,
            account_id=account_id,
            status="PENDING",
            expires_at=at + timedelta(seconds=cfg["APPROVAL_TTL_SECONDS"]),
            created_at=at,
        )
        db.session.add(approval)
        db.session.flush()
        new_payee = any(s.get("code") == "NEW_PAYEE" for s in signals)
        new_device = any(s.get("code") == "UNTRUSTED_DEVICE" for s in signals)
        where = f" in {city}" if city else ""
        notifier.send(
            account.customer_id,
            "APP",
            "Was this you?",
            f"Someone tried to send {amount_txt} to a {'NEW ' if new_payee else ''}payee "
            f"({payee.payee_name}) from a {'NEW ' if new_device else ''}device{where}. "
            "We stopped it. Was this you?",
            kind="APPROVAL",
            ref_id=approval.id,
        )
    else:
        otp = f"{secrets.randbelow(1_000_000):06d}"
        otp_req.otp_hash = _hash_otp(otp_req.id, otp)
        otp_req.expires_at = at + timedelta(seconds=cfg["OTP_TTL_SECONDS"])
        if decision == "OTP_SENT_WITH_WARNING":
            is_new = any(s.get("code") == "NEW_PAYEE" for s in signals)
            body = (
                f"OTP {otp} is to SEND {amount_txt} to {payee.payee_name}"
                f"{' (NEW payee)' if is_new else ''}. If you did not start this, DO NOT share it. "
                "The bank never asks for OTP on calls."
            )
        else:
            body = (
                f"OTP {otp} to send {amount_txt} to {payee.payee_name}. Valid for 3 minutes. "
                "Never share your OTP with anyone."
            )
        notifier.send(account.customer_id, "SMS", "Your OTP", body, kind="OTP", ref_id=otp_req.id)

    db.session.commit()
    current_app.logger.info(
        "OTP Shield: account %s amount %s points=%s -> %s", account_id, amount, otp_req.risk_points, decision
    )
    return {
        "otp_request_id": otp_req.id,
        "decision": decision,
        "risk_points": otp_req.risk_points,
        "signals": signals,
        "approval_id": approval.id if approval else None,
        "expires_at": (otp_req.expires_at or (approval.expires_at if approval else None)).isoformat(),
        "message": REQUESTER_MESSAGES[decision],
    }


def execute_payment(otp_req, device_id, ip_address=None, city=None):
    """Runs the payment an OTP request was for through the fraud engine."""
    result = fraud_engine.ingest(
        {
            "external_ref": f"BANK-OTP-{otp_req.id}",
            "account_id": otp_req.account_id,
            "beneficiary_id": otp_req.beneficiary_id,
            "otp_request_id": otp_req.id,
            "amount": otp_req.amount,
            "channel": "NETBANKING",
            "city": city or otp_req.city,
            "device_id": device_id,
            "ip_address": ip_address or otp_req.ip_address,
            "source": "BANK_DEMO",
        },
        source="BANK_DEMO",
    )
    # The fraud engine moved (or held) the money with its decision.
    db.session.execute(
        text("UPDATE otp_requests SET txn_id = :t WHERE id = :o"), {"t": result["txn_id"], "o": otp_req.id}
    )
    db.session.commit()
    return result


def verify_otp(otp_request_id, otp, device_id, account_id=None, ip_address=None, city=None):
    cfg = current_app.config
    otp_req = db.session.get(OtpRequest, otp_request_id)
    if otp_req is None or (account_id is not None and otp_req.account_id != account_id):
        raise AppError("We couldn't find that OTP request.", "OTP_NOT_FOUND", 404)
    if otp_req.decision == "OTP_BLOCKED_APPROVAL_REQUIRED" or not otp_req.otp_hash:
        raise AppError("No OTP was sent for this payment. Approve it in the app instead.", "NO_OTP", 400)
    if otp_req.final_status == "VERIFIED":
        raise AppError("This OTP was already used.", "OTP_USED", 409)
    if otp_req.final_status != "PENDING":
        raise AppError("This OTP can no longer be used. Please start again.", "OTP_CLOSED", 410)

    now = datetime.now()
    if otp_req.expires_at and otp_req.expires_at < now:
        otp_req.final_status = "EXPIRED"
        db.session.commit()
        raise AppError("This OTP has expired. Please request a new one.", "OTP_EXPIRED", 410)

    otp_req.attempts += 1
    if not hmac.compare_digest(otp_req.otp_hash, _hash_otp(otp_req.id, otp)):
        remaining = cfg["OTP_MAX_VERIFY_ATTEMPTS"] - otp_req.attempts
        if remaining <= 0:
            otp_req.final_status = "LOCKED"
            db.session.commit()
            raise AppError("Wrong OTP entered 3 times. This payment is cancelled.", "OTP_LOCKED", 429)
        db.session.commit()
        raise AppError(
            f"Wrong OTP. {remaining} attempt{'s' if remaining != 1 else ''} left.", "OTP_WRONG", 400
        )

    otp_req.final_status = "VERIFIED"
    otp_req.verified_at = now
    otp_req.verified_device_id = device_id
    otp_req.verified_ip = ip_address
    _log_session(otp_req.account_id, "OTP_VERIFY", device_id, ip_address, city, now)
    db.session.commit()
    payment = execute_payment(otp_req, device_id, ip_address, city)
    return {"verified": True, "payment": payment}


def respond_approval(approval_id, answer, device_id):
    approval = db.session.get(DeviceApproval, approval_id)
    if approval is None:
        raise AppError("We couldn't find that approval request.", "APPROVAL_NOT_FOUND", 404)
    if approval.status != "PENDING":
        raise AppError("This request was already answered.", "APPROVAL_CLOSED", 409)
    now = datetime.now()
    otp_req = db.session.get(OtpRequest, approval.otp_request_id)
    if approval.expires_at < now:
        approval.status = "EXPIRED"
        otp_req.final_status = "EXPIRED"
        db.session.commit()
        raise AppError("This request expired. The payment was not made.", "APPROVAL_EXPIRED", 410)
    if not _is_trusted(approval.account_id, device_id):
        raise AppError(
            "Approvals can only be answered from your registered phone.", "UNTRUSTED_DEVICE", 403
        )

    account = db.session.get(Account, approval.account_id)
    approval.responded_at = now
    approval.responded_device_id = device_id
    notifier = get_notifier()

    if answer == "NO":
        return _deny(approval, otp_req, account, notifier, now)

    # YES: the customer vouches for the new device -> trust it and pay,
    # still through the normal fraud engine.
    approval.status = "APPROVED"
    otp_req.final_status = "APPROVED"
    device = Device.query.filter_by(account_id=account.id, device_id=otp_req.requesting_device_id).first()
    if device is None:
        device = Device(
            account_id=account.id,
            device_id=otp_req.requesting_device_id,
            device_label="Approved from your registered phone",
            first_seen=now,
            last_seen=now,
        )
        db.session.add(device)
    device.is_trusted = True
    notifier.send(
        account.customer_id,
        "APP",
        "Payment approved",
        f"Thanks for confirming. Your new device is now trusted and the payment of "
        f"{inr(otp_req.amount)} is being processed.",
        kind="INFO",
        ref_id=otp_req.id,
    )
    db.session.commit()
    payment = execute_payment(otp_req, otp_req.requesting_device_id)
    return {"status": "APPROVED", "payment": payment}


def _deny(approval, otp_req, account, notifier, now):
    approval.status = "DENIED"
    otp_req.final_status = "DENIED"

    # Log the intruder's device out of this account.
    db.session.execute(
        text(
            "UPDATE sessions SET is_active = 0 "
            "WHERE account_id = :a AND device_id = :d AND is_active = 1"
        ),
        {"a": account.id, "d": otp_req.requesting_device_id},
    )
    # Freeze the payee for 24 hours.
    payee = db.session.get(Beneficiary, otp_req.beneficiary_id)
    if payee:
        payee.cooling_until = now + timedelta(hours=24)

    # Blacklist everything the fraudster used.
    set_actor("otp-shield")
    reason = f"Customer said NO to OTP Shield approval #{approval.id}"
    entries = [("DEVICE", otp_req.requesting_device_id), ("IP", otp_req.ip_address)]
    if payee:
        entries.append(("ACCOUNT", payee.payee_account_no))
    added = []
    for entry_type, value in entries:
        if not value:
            continue
        db.session.execute(
            text(
                "INSERT IGNORE INTO watchlist (entry_type, entry_value, reason, added_by, added_at) "
                "VALUES (:t, :v, :r, 'otp-shield', :at)"
            ),
            {"t": entry_type, "v": value, "r": reason, "at": now},
        )
        added.append({"entry_type": entry_type, "entry_value": value})

    alert = Alert(
        otp_request_id=otp_req.id,
        source="OTP_SHIELD",
        summary=f"Customer denied {inr(otp_req.amount)} to {payee.payee_name if payee else 'a payee'} — likely OTP scam",
        risk_score=min(100, max(70, otp_req.risk_points)),
        priority="HIGH",
        alert_status="OPEN",
        created_at=now,
        updated_at=now,
    )
    db.session.add(alert)
    db.session.flush()
    db.session.add(Case(alert_id=alert.id, created_at=now))
    notifier.send(
        account.customer_id,
        "APP",
        "We blocked it",
        f"Thank you. The payment of {inr(otp_req.amount)} was blocked, the unknown device was "
        "logged out and reported. Your money is safe. Consider changing your password.",
        kind="INFO",
        ref_id=otp_req.id,
    )
    db.session.commit()
    set_actor(None)
    return {"status": "DENIED", "watchlisted": added, "alert_id": alert.id}


def request_status(otp_request_id, account_id=None):
    otp_req = db.session.get(OtpRequest, otp_request_id)
    if otp_req is None or (account_id is not None and otp_req.account_id != account_id):
        raise AppError("We couldn't find that request.", "OTP_NOT_FOUND", 404)
    approval = DeviceApproval.query.filter_by(otp_request_id=otp_req.id).first()
    payment = None
    if otp_req.txn_id:
        txn = db.session.get(Transaction, otp_req.txn_id)
        if txn:
            payment = fraud_engine.decision_payload(txn)
    data = otp_req.to_dict()
    data["approval"] = approval.to_dict() if approval else None
    data["payment"] = payment
    return data


def expire_stale(now=None):
    """Scheduler job: closes OTPs and approvals that ran out of time."""
    now = now or datetime.now()
    otps = db.session.execute(
        text(
            "UPDATE otp_requests SET final_status = 'EXPIRED' "
            "WHERE final_status = 'PENDING' AND expires_at IS NOT NULL AND expires_at < :now"
        ),
        {"now": now},
    ).rowcount
    db.session.execute(
        text(
            "UPDATE otp_requests o JOIN device_approvals da ON da.otp_request_id = o.id "
            "SET o.final_status = 'EXPIRED' "
            "WHERE da.status = 'PENDING' AND da.expires_at < :now AND o.final_status = 'PENDING'"
        ),
        {"now": now},
    )
    approvals = db.session.execute(
        text("UPDATE device_approvals SET status = 'EXPIRED' WHERE status = 'PENDING' AND expires_at < :now"),
        {"now": now},
    ).rowcount
    db.session.commit()
    return {"otps": otps, "approvals": approvals}
