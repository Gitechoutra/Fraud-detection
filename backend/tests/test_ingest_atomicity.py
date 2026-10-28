"""Insert + evaluate + commit is one atomic unit, and ingestion is idempotent."""

import pytest

from portal.helpers.db_helpers import scalar
from portal.helpers.responses import AppError
from portal.services import fraud_engine
from tests.conftest import auth, make_account, pay, staff_token


def test_duplicate_external_ref_returns_existing_decision():
    acc = make_account()
    first = pay(acc, 1000, external_ref="DUP-1")
    second = pay(acc, 99999, external_ref="DUP-1")  # different body, same ref
    assert second["duplicate"] is True
    assert second["txn_id"] == first["txn_id"]
    assert second["amount"] == 1000.0
    assert scalar("SELECT COUNT(*) FROM transactions WHERE external_ref = 'DUP-1'") == 1


def test_failure_inside_evaluation_rolls_everything_back(monkeypatch):
    acc = make_account()
    before = scalar("SELECT COUNT(*) FROM transactions")

    def boom(name, args=()):
        raise RuntimeError("simulated crash during evaluation")

    monkeypatch.setattr(fraud_engine, "call_procedure", boom)
    with pytest.raises(RuntimeError):
        pay(acc, 1000, external_ref="CRASH-1")
    assert scalar("SELECT COUNT(*) FROM transactions") == before
    assert scalar("SELECT COUNT(*) FROM transactions WHERE external_ref = 'CRASH-1'") == 0


def test_failure_after_evaluation_leaves_no_evidence(monkeypatch):
    """Even if the procedure ran (hits/alerts written), a later error undoes it all."""
    acc = make_account()
    real_call = fraud_engine.call_procedure

    def crash_after_procedure(name, args=()):
        real_call(name, args)  # rule hits, alert and case are written...
        raise RuntimeError("simulated crash after evaluation")  # ...then something fails

    monkeypatch.setattr(fraud_engine, "call_procedure", crash_after_procedure)
    with pytest.raises(RuntimeError):
        pay(acc, 30000, device_id="DEV-STOLEN-0001", external_ref="CRASH-2")
    assert scalar("SELECT COUNT(*) FROM transactions WHERE external_ref = 'CRASH-2'") == 0
    assert scalar("SELECT COUNT(*) FROM rule_hits") == 0
    assert scalar("SELECT COUNT(*) FROM alerts") == 0


def test_unknown_account_is_rejected():
    with pytest.raises(AppError) as exc:
        fraud_engine.ingest({"external_ref": "X-1", "account_id": 999999, "amount": 10, "channel": "UPI"})
    assert exc.value.status == 404


def test_api_ingest_201_then_200_for_duplicate(client):
    acc = make_account()
    body = {"external_ref": "API-1", "account_no": acc.account_no, "amount": 750, "channel": "CARD",
            "city": "Hyderabad", "device_id": "DEV-T-1"}
    headers = {"X-API-Key": "dev-ingest-key"}
    first = client.post("/api/transactions", json=body, headers=headers)
    assert first.status_code == 201
    data = first.get_json()["data"]
    assert data["status"] == "APPROVED" and data["duplicate"] is False
    again = client.post("/api/transactions", json=body, headers=headers)
    assert again.status_code == 200
    assert again.get_json()["data"]["txn_id"] == data["txn_id"]


def test_api_ingest_validation_error(client):
    res = client.post("/api/transactions", json={"external_ref": "BAD", "amount": -5, "channel": "PIGEON"},
                      headers={"X-API-Key": "dev-ingest-key"})
    assert res.status_code == 422
    body = res.get_json()
    assert body["ok"] is False and body["error"]["code"] == "VALIDATION_ERROR"
    assert "amount" in body["error"]["details"] and "channel" in body["error"]["details"]


def test_api_ingest_requires_key_or_admin(client):
    acc = make_account()
    body = {"external_ref": "API-2", "account_id": acc.id, "amount": 10, "channel": "UPI"}
    assert client.post("/api/transactions", json=body).status_code == 401
    assert client.post("/api/transactions", json=body, headers={"X-API-Key": "wrong"}).status_code == 401
    token = staff_token(client, "analyst", "Analyst@123")
    assert client.post("/api/transactions", json=body, headers=auth(token)).status_code == 403
    token = staff_token(client)
    assert client.post("/api/transactions", json=body, headers=auth(token)).status_code == 201


def test_bulk_csv_upload(client):
    acc = make_account()
    csv_text = (
        "external_ref,account_no,amount,channel,city,device_id\n"
        f"CSV-1,{acc.account_no},500,UPI,Hyderabad,DEV-T-1\n"
        f"CSV-2,{acc.account_no},abc,UPI,Hyderabad,DEV-T-1\n"
        f"CSV-1,{acc.account_no},500,UPI,Hyderabad,DEV-T-1\n"
    )
    import io

    res = client.post(
        "/api/transactions/bulk",
        data={"file": (io.BytesIO(csv_text.encode()), "batch.csv")},
        headers={"X-API-Key": "dev-ingest-key"},
        content_type="multipart/form-data",
    )
    assert res.status_code == 200
    summary = res.get_json()["data"]
    assert summary["rows"] == 3 and summary["approved"] == 1 and summary["duplicates"] == 1
    assert len(summary["errors"]) == 1 and summary["errors"][0]["line"] == 3
