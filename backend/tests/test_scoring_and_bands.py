"""Score = LEAST(100, SUM(weights)); bands decide APPROVED / REVIEW / BLOCKED;
REVIEW/BLOCKED create an alert and a case."""

from datetime import timedelta

import pytest

from portal.extensions import db
from portal.helpers.db_helpers import fetch_one, scalar
from portal.models import Account, FraudRule, SystemSetting
from tests.conftest import NOON, fired, make_account, pay


def _set_weight(code, weight):
    db.session.get(FraudRule, code).weight = weight
    db.session.commit()


def _night_payment(weight):
    """A payment that fires only R5, with R5 weighted `weight`."""
    _set_weight("R5", weight)
    acc = make_account(avg=5000)
    return pay(acc, 15000, at=NOON.replace(hour=2))


@pytest.mark.parametrize("weight,status", [(0, "APPROVED"), (39, "APPROVED"), (40, "REVIEW"),
                                           (69, "REVIEW"), (70, "BLOCKED"), (100, "BLOCKED")])
def test_band_boundaries(weight, status):
    result = _night_payment(weight)
    assert fired(result) == {"R5"}
    assert result["risk_score"] == weight
    assert result["status"] == status


def test_score_is_sum_of_fired_weights():
    _set_weight("R1", 30)
    _set_weight("R4", 20)
    acc = make_account(avg=2000, history=10)
    result = pay(acc, 30000, device_id="BRAND-NEW")
    assert fired(result) == {"R1", "R4"}
    assert result["risk_score"] == 50
    assert result["status"] == "REVIEW"


def test_score_is_capped_at_100():
    for code, weight in (("R1", 30), ("R4", 20), ("R5", 10), ("R6", 50)):
        _set_weight(code, weight)
    acc = make_account(avg=2000, history=10)
    # 30 + 20 + 10 + 50 = 110 -> capped at 100
    result = pay(acc, 30000, device_id="DEV-STOLEN-0001", at=NOON.replace(hour=3))
    assert {"R1", "R4", "R5", "R6"} <= fired(result)
    assert result["risk_score"] == 100
    assert result["status"] == "BLOCKED"


def test_approved_payment_has_no_alert():
    acc = make_account()
    result = pay(acc, 1000)
    assert result["status"] == "APPROVED" and result["alert_id"] is None
    assert scalar("SELECT COUNT(*) FROM alerts") == 0


def test_review_creates_medium_alert_and_case():
    result = _night_payment(45)
    alert = fetch_one("SELECT * FROM alerts WHERE id = :id", {"id": result["alert_id"]})
    assert alert["priority"] == "MEDIUM" and alert["alert_status"] == "OPEN"
    assert alert["txn_id"] == result["txn_id"]
    assert scalar("SELECT COUNT(*) FROM cases WHERE alert_id = :id", {"id": alert["id"]}) == 1


def test_blocked_creates_high_alert_and_customer_message():
    result = _night_payment(80)
    alert = fetch_one("SELECT * FROM alerts WHERE id = :id", {"id": result["alert_id"]})
    assert alert["priority"] == "HIGH"
    assert "Blocked" in alert["summary"]
    # The TEST source is not silent, so the customer got a "Was this you?" SMS.
    assert scalar("SELECT COUNT(*) FROM notifications WHERE kind = 'ALERT' AND ref_id = :t",
                  {"t": result["txn_id"]}) == 1


def test_bands_are_read_from_settings():
    db.session.get(SystemSetting, "REVIEW_THRESHOLD").setting_value = "5"
    db.session.commit()
    result = _night_payment(10)
    assert result["status"] == "REVIEW"


def test_last_txn_at_updated_only_for_approved():
    _set_weight("R8", 20)  # R8 alone stays below the hold score
    acc = make_account(history=0, last_txn_days=200, status="DORMANT")
    before = acc.last_txn_at
    assert pay(acc, 25000)["status"] == "APPROVED"
    db.session.expire_all()
    assert db.session.get(Account, acc.id).last_txn_at > before
    assert db.session.get(Account, acc.id).status == "ACTIVE"

    acc2 = make_account(history=0, last_txn_days=200, status="DORMANT")
    _set_weight("R8", 75)
    before2 = acc2.last_txn_at
    assert pay(acc2, 25000)["status"] == "BLOCKED"
    db.session.expire_all()
    fresh = db.session.get(Account, acc2.id)
    assert fresh.last_txn_at == before2 and fresh.status == "DORMANT"


def test_stage_timings_and_decision_time_recorded():
    acc = make_account()
    result = pay(acc, 500, at=NOON + timedelta(minutes=1))
    assert set(result["stage_timings"]) == {"ingest", "save", "rules", "score", "decide", "alert"}
    assert result["decision_ms"] > 0
    row = fetch_one("SELECT decision_ms, stage_timings FROM transactions WHERE id = :id", {"id": result["txn_id"]})
    assert float(row["decision_ms"]) == pytest.approx(result["decision_ms"])
