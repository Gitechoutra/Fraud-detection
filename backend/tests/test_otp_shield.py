"""OTP Shield (R9-A): three decision levels, YES/NO approvals, OTP limits,
and the full demo-bank API flow with Ravi."""

import re
from datetime import datetime, timedelta

import pytest

from portal.extensions import db
from portal.helpers.db_helpers import fetch_all, scalar
from portal.helpers.responses import AppError
from portal.models import Beneficiary, Device, OtpRequest, SessionEvent
from portal.seeders import seed_demo_story
from portal.seeders.seed_demo_story import RAVI, ravi_account
from portal.services import otp_shield
from portal.services.simulator import ip_for_device

RAVI_IP = ip_for_device(RAVI["device_id"])


@pytest.fixture
def ravi():
    seed_demo_story.run(log=lambda *_: None)
    _, account = ravi_account()
    return account


def _existing_payee(account):
    return Beneficiary.query.filter_by(account_id=account.id).order_by(Beneficiary.added_at).first()


def _new_payee(account, device, name="Kumar", acc_no="77001234567890"):
    payee = Beneficiary(account_id=account.id, payee_name=name, payee_account_no=acc_no,
                        payee_ifsc="PUNB0123400", added_at=datetime.now() - timedelta(minutes=1),
                        added_device_id=device)
    db.session.add(payee)
    db.session.commit()
    return payee


def _fraudster_setup(account, device="SCAM-PHONE-1"):
    db.session.add(SessionEvent(account_id=account.id, device_id=device, ip_address="103.21.4.9", city="Delhi",
                                event_type="LOGIN", created_at=datetime.now() - timedelta(minutes=3)))
    db.session.commit()
    return _new_payee(account, device)


def _otp_from_sms(account):
    body = fetch_all(
        "SELECT body FROM notifications n JOIN accounts a ON a.customer_id = n.customer_id "
        "WHERE a.id = :a AND n.kind = 'OTP' ORDER BY n.id DESC LIMIT 1", {"a": account.id})[0]["body"]
    return re.search(r"OTP (\d{6})", body).group(1), body


# --- three decision levels ------------------------------------------------

def test_low_risk_sends_normal_otp_and_payment_goes_through(ravi):
    payee = _existing_payee(ravi)
    res = otp_shield.request_otp(ravi.id, payee.id, 2000, RAVI["device_id"], RAVI_IP, "Hyderabad")
    assert res["decision"] == "OTP_SENT" and res["risk_points"] < 20
    otp, body = _otp_from_sms(ravi)
    assert "Never share" in body
    stored = db.session.get(OtpRequest, res["otp_request_id"])
    assert stored.otp_hash and otp not in stored.otp_hash  # only a hash is stored
    out = otp_shield.verify_otp(res["otp_request_id"], otp, RAVI["device_id"], account_id=ravi.id)
    assert out["verified"] and out["payment"]["status"] == "APPROVED"


def test_medium_risk_sends_otp_with_explicit_warning(ravi):
    payee = _new_payee(ravi, RAVI["device_id"])
    res = otp_shield.request_otp(ravi.id, payee.id, 10000, RAVI["device_id"], RAVI_IP, "Hyderabad")
    assert res["decision"] == "OTP_SENT_WITH_WARNING"
    assert 20 <= res["risk_points"] < 40
    assert {s["code"] for s in res["signals"]} == {"NEW_PAYEE", "LARGE_AMOUNT"}
    otp, body = _otp_from_sms(ravi)
    assert "SEND ₹10,000 to Kumar (NEW payee)" in body
    assert "DO NOT share" in body and "never asks for OTP on calls" in body
    out = otp_shield.verify_otp(res["otp_request_id"], otp, RAVI["device_id"], account_id=ravi.id)
    assert out["payment"]["status"] == "APPROVED"
    assert "R9" not in {h["rule_code"] for h in out["payment"]["rules"]}


def test_high_risk_sends_no_otp_and_asks_trusted_phone(ravi):
    payee = _fraudster_setup(ravi)
    res = otp_shield.request_otp(ravi.id, payee.id, 48000, "SCAM-PHONE-1", "103.21.4.9", "Delhi")
    assert res["decision"] == "OTP_BLOCKED_APPROVAL_REQUIRED"
    assert res["risk_points"] >= 40
    assert {"UNTRUSTED_DEVICE", "NEW_PAYEE", "NEW_DEVICE_LOGIN", "NEW_LOCATION", "LARGE_AMOUNT"} <= {
        s["code"] for s in res["signals"]}
    assert res["message"] == "Approve this payment in the app on your registered phone."
    stored = db.session.get(OtpRequest, res["otp_request_id"])
    assert stored.otp_hash is None  # no OTP exists at all
    assert scalar("SELECT COUNT(*) FROM notifications WHERE kind = 'OTP'") == 0
    app_msg = fetch_all("SELECT body FROM notifications WHERE kind = 'APPROVAL'")[0]["body"]
    assert "₹48,000" in app_msg and "NEW payee" in app_msg and "NEW device" in app_msg and "Delhi" in app_msg
    with pytest.raises(AppError) as exc:
        otp_shield.verify_otp(res["otp_request_id"], "123456", "SCAM-PHONE-1", account_id=ravi.id)
    assert exc.value.code == "NO_OTP"


def test_watchlisted_ip_alone_blocks_otp(ravi):
    payee = _existing_payee(ravi)
    res = otp_shield.request_otp(ravi.id, payee.id, 1000, RAVI["device_id"], "185.220.101.4", "Hyderabad")
    assert res["decision"] == "OTP_BLOCKED_APPROVAL_REQUIRED"
    assert any(s["code"] == "WATCHLIST" for s in res["signals"])


# --- YES / NO ---------------------------------------------------------------

def test_customer_says_no(ravi):
    payee = _fraudster_setup(ravi)
    res = otp_shield.request_otp(ravi.id, payee.id, 48000, "SCAM-PHONE-1", "103.21.4.9", "Delhi")
    out = otp_shield.respond_approval(res["approval_id"], "NO", RAVI["device_id"])
    assert out["status"] == "DENIED"
    values = {(w["entry_type"], w["entry_value"]) for w in out["watchlisted"]}
    assert values == {("DEVICE", "SCAM-PHONE-1"), ("IP", "103.21.4.9"), ("ACCOUNT", "77001234567890")}
    assert scalar("SELECT COUNT(*) FROM watchlist WHERE added_by = 'otp-shield'") == 3
    assert scalar("SELECT COUNT(*) FROM sessions WHERE device_id = 'SCAM-PHONE-1' AND is_active = 1") == 0
    db.session.expire_all()
    assert db.session.get(Beneficiary, payee.id).cooling_until > datetime.now() + timedelta(hours=23)
    alert = fetch_all("SELECT * FROM alerts WHERE id = :id", {"id": out["alert_id"]})[0]
    assert alert["priority"] == "HIGH" and alert["source"] == "OTP_SHIELD"
    assert scalar("SELECT COUNT(*) FROM cases WHERE alert_id = :id", {"id": out["alert_id"]}) == 1
    assert scalar("SELECT COUNT(*) FROM transactions WHERE account_id = :a AND source = 'BANK_DEMO'",
                  {"a": ravi.id}) == 0
    # The payee is now on a 24-hour hold.
    with pytest.raises(AppError) as exc:
        otp_shield.request_otp(ravi.id, payee.id, 1000, RAVI["device_id"], RAVI_IP, "Hyderabad")
    assert exc.value.status == 423


def test_customer_says_yes(ravi):
    payee = _fraudster_setup(ravi, device="RAVI-NEW-PHONE")
    res = otp_shield.request_otp(ravi.id, payee.id, 12000, "RAVI-NEW-PHONE", "103.21.4.9", "Delhi")
    assert res["decision"] == "OTP_BLOCKED_APPROVAL_REQUIRED"
    out = otp_shield.respond_approval(res["approval_id"], "YES", RAVI["device_id"])
    assert out["status"] == "APPROVED"
    assert Device.query.filter_by(account_id=ravi.id, device_id="RAVI-NEW-PHONE", is_trusted=True).first()
    rules = {h["rule_code"] for h in out["payment"]["rules"]}
    assert "R4" not in rules and "R9" not in rules  # the device is trusted now
    assert out["payment"]["status"] == "APPROVED"


def test_approval_must_come_from_trusted_device(ravi):
    payee = _fraudster_setup(ravi)
    res = otp_shield.request_otp(ravi.id, payee.id, 48000, "SCAM-PHONE-1", "103.21.4.9", "Delhi")
    with pytest.raises(AppError) as exc:
        otp_shield.respond_approval(res["approval_id"], "YES", "SCAM-PHONE-1")
    assert exc.value.status == 403


def test_expired_approval_cannot_be_answered(ravi):
    payee = _fraudster_setup(ravi)
    res = otp_shield.request_otp(ravi.id, payee.id, 48000, "SCAM-PHONE-1", "103.21.4.9", "Delhi",
                                 at=datetime.now() - timedelta(minutes=10))
    with pytest.raises(AppError) as exc:
        otp_shield.respond_approval(res["approval_id"], "YES", RAVI["device_id"])
    assert exc.value.code == "APPROVAL_EXPIRED"


# --- OTP limits -------------------------------------------------------------

def test_three_wrong_otps_lock_the_payment(ravi):
    payee = _existing_payee(ravi)
    res = otp_shield.request_otp(ravi.id, payee.id, 2000, RAVI["device_id"], RAVI_IP, "Hyderabad")
    otp, _ = _otp_from_sms(ravi)
    wrong = "000000" if otp != "000000" else "111111"
    for expected in ("OTP_WRONG", "OTP_WRONG", "OTP_LOCKED"):
        with pytest.raises(AppError) as exc:
            otp_shield.verify_otp(res["otp_request_id"], wrong, RAVI["device_id"], account_id=ravi.id)
        assert exc.value.code == expected
    with pytest.raises(AppError):
        otp_shield.verify_otp(res["otp_request_id"], otp, RAVI["device_id"], account_id=ravi.id)


def test_expired_otp_is_rejected(ravi):
    payee = _existing_payee(ravi)
    res = otp_shield.request_otp(ravi.id, payee.id, 2000, RAVI["device_id"], RAVI_IP, "Hyderabad",
                                 at=datetime.now() - timedelta(minutes=5))
    otp, _ = _otp_from_sms(ravi)
    with pytest.raises(AppError) as exc:
        otp_shield.verify_otp(res["otp_request_id"], otp, RAVI["device_id"], account_id=ravi.id)
    assert exc.value.code == "OTP_EXPIRED"


def test_rate_limit_five_requests_per_ten_minutes(ravi):
    payee = _existing_payee(ravi)
    for _ in range(5):
        otp_shield.request_otp(ravi.id, payee.id, 500, RAVI["device_id"], RAVI_IP, "Hyderabad")
    with pytest.raises(AppError) as exc:
        otp_shield.request_otp(ravi.id, payee.id, 500, RAVI["device_id"], RAVI_IP, "Hyderabad")
    assert exc.value.status == 429


def test_scheduler_expires_stale_requests(ravi):
    payee = _fraudster_setup(ravi)
    otp_shield.request_otp(ravi.id, payee.id, 48000, "SCAM-PHONE-1", "103.21.4.9", "Delhi",
                           at=datetime.now() - timedelta(minutes=10))
    result = otp_shield.expire_stale()
    assert result["approvals"] == 1
    assert scalar("SELECT COUNT(*) FROM device_approvals WHERE status = 'EXPIRED'") == 1


# --- the demo bank app, end to end over HTTP --------------------------------

def _bank_login(client, device, city, ip):
    res = client.post("/api/bank-demo/login", json={
        "netbanking_id": RAVI["netbanking_id"], "password": RAVI["password"],
        "device_id": device, "ip_address": ip, "city": city})
    assert res.status_code == 200, res.get_json()
    data = res.get_json()["data"]
    return {"Authorization": f"Bearer {data['token']}"}, data


def test_full_story_over_the_api(client, ravi):
    # Fraudster's phone: stolen password, new device, Delhi.
    scam, profile = _bank_login(client, "SCAM-PHONE-9", "Delhi", "103.44.5.6")
    assert profile["device"]["is_trusted"] is False
    payee = client.post("/api/bank-demo/payees", json={
        "payee_name": "Kumar", "payee_account_no": "77001234567890", "payee_ifsc": "PUNB0123400"},
        headers=scam).get_json()["data"]
    sent = client.post("/api/bank-demo/send", json={"beneficiary_id": payee["id"], "amount": 48000}, headers=scam)
    assert sent.status_code == 201
    sent = sent.get_json()["data"]
    assert sent["decision"] == "OTP_BLOCKED_APPROVAL_REQUIRED"

    # Ravi's phone: sees the approval and taps NO.
    mine, profile = _bank_login(client, RAVI["device_id"], "Hyderabad", RAVI_IP)
    assert profile["device"]["is_trusted"] is True
    pending = client.get("/api/otp/approval/pending", headers=mine).get_json()["data"]
    assert len(pending) == 1 and pending[0]["id"] == sent["approval_id"]
    notes = client.get("/api/notifications", headers=mine).get_json()["data"]
    assert notes[0]["kind"] == "APPROVAL"
    # The fraudster can't answer it.
    assert client.post(f"/api/otp/approval/{sent['approval_id']}/respond", json={"answer": "YES"},
                       headers=scam).status_code == 403
    answered = client.post(f"/api/otp/approval/{sent['approval_id']}/respond", json={"answer": "NO"}, headers=mine)
    assert answered.get_json()["data"]["status"] == "DENIED"

    status = client.get(f"/api/otp/request/{sent['otp_request_id']}/status", headers=scam).get_json()["data"]
    assert status["final_status"] == "DENIED" and status["approval"]["status"] == "DENIED"

    # Genuine path: Ravi pays Amma from his own phone with a normal OTP.
    amma = _existing_payee(ravi)
    sent = client.post("/api/bank-demo/send", json={"beneficiary_id": amma.id, "amount": 2000},
                       headers=mine).get_json()["data"]
    assert sent["decision"] == "OTP_SENT"
    otp, _ = _otp_from_sms(ravi)
    done = client.post("/api/otp/verify", json={"otp_request_id": sent["otp_request_id"], "otp": otp},
                       headers=mine).get_json()["data"]
    assert done["payment"]["status"] == "APPROVED"


def test_demo_reset_restores_ravi(client, ravi):
    from tests.conftest import auth, staff_token

    payee = _fraudster_setup(ravi)
    res = otp_shield.request_otp(ravi.id, payee.id, 48000, "SCAM-PHONE-1", "103.21.4.9", "Delhi")
    otp_shield.respond_approval(res["approval_id"], "NO", RAVI["device_id"])
    token = staff_token(client, "analyst", "Analyst@123")
    assert client.post("/api/bank-demo/reset", headers=auth(token)).status_code == 200
    assert scalar("SELECT COUNT(*) FROM watchlist WHERE added_by = 'otp-shield'") == 0
    assert scalar("SELECT COUNT(*) FROM beneficiaries WHERE account_id = :a", {"a": ravi.id}) == 2
    assert scalar("SELECT COUNT(*) FROM otp_requests") == 0


def test_bank_token_cannot_use_staff_endpoints(client, ravi):
    mine, _ = _bank_login(client, RAVI["device_id"], "Hyderabad", RAVI_IP)
    assert client.get("/api/dashboard/summary", headers=mine).status_code == 403
    assert client.get("/api/auth/me", headers=mine).status_code == 401
