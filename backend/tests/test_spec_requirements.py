"""Specification points added after the comparison with the project document:
specification weights, the tamper-evident audit log, R9 follow-up actions,
the external model-score hook, fraud rate by channel/city and the index
benchmark. (Rule-combination stories, explainability and alert visibility
are covered in test_simulator_and_evaluator.py.)"""

import csv
import json
import os
import re
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from portal.extensions import db
from portal.helpers.db_helpers import fetch_all, load_sql_objects, scalar
from portal.helpers.responses import AppError
from portal.models import Account, Beneficiary, Case, FraudRule, SessionEvent
from portal.seeders import seed_customers, seed_rules, seed_transactions
from portal.services import (audit_chain, dataset, eval_report, evaluator, index_benchmark, otp_shield, schema_ddl,
                             simulator)
from tests.conftest import NOON, auth, fired, make_account, make_payee, pay, quiet, staff_token

TABLE_4_4 = {"R1": 30, "R2": 25, "R3": 35, "R4": 20, "R5": 10, "R6": 50, "R7": 15, "R8": 20, "R9": 45}


def _set(key, value):
    db.session.execute(text("UPDATE system_settings SET setting_value = :v WHERE setting_key = :k"),
                       {"v": str(value), "k": key})
    db.session.commit()


# --- 1. rule weights (Table 4.4) -------------------------------------------

def test_specification_weights_are_kept_and_can_be_restored(client):
    rules = client.get("/api/rules", headers=auth(staff_token(client, "risk"))).get_json()["data"]["rules"]
    assert {r["rule_code"]: r["spec_weight"] for r in rules} == TABLE_4_4
    seed_rules.reset_rules(spec_weights=True)
    assert {r.rule_code: r.weight for r in FraudRule.query.all()} == TABLE_4_4
    seed_rules.reset_rules()
    assert db.session.get(FraudRule, "R1").weight == 40


# --- 4. tamper-evident audit log -------------------------------------------

def _audit_some_changes(client):
    t = auth(staff_token(client, "risk"))
    for weight in (41, 42, 43):
        assert client.put("/api/rules/R1", json={"weight": weight}, headers=t).status_code == 200


def test_audit_chain_links_every_entry_and_verifies(client):
    _audit_some_changes(client)
    rows = fetch_all("SELECT prev_hash, row_hash FROM audit_log WHERE entity = 'fraud_rules' ORDER BY id")
    assert len(rows) >= 3 and all(r["row_hash"] for r in rows)
    assert all(b["prev_hash"] == a["row_hash"] for a, b in zip(rows, rows[1:]))
    res = client.get("/api/audit/verify", headers=auth(staff_token(client, "risk"))).get_json()["data"]
    assert res["intact"] and res["rows"] == scalar("SELECT COUNT(*) FROM audit_log")


def test_audit_entries_cannot_be_changed_or_deleted(client):
    _audit_some_changes(client)
    for sql in ("UPDATE audit_log SET actor = 'someone-else'", "DELETE FROM audit_log"):
        with pytest.raises(OperationalError, match="append-only"):
            db.session.execute(text(sql))
        db.session.rollback()
    assert audit_chain.verify()["intact"]


def test_audit_tampering_is_detected():
    db.session.execute(text("UPDATE fraud_rules SET weight = 41 WHERE rule_code = 'R2'"))
    db.session.execute(text("UPDATE fraud_rules SET weight = 42 WHERE rule_code = 'R2'"))
    db.session.commit()
    first = scalar("SELECT MIN(id) FROM audit_log")
    # Someone with full database rights removes the guard and edits history.
    db.session.execute(text("DROP TRIGGER trg_audit_log_no_update"))
    try:
        db.session.execute(text("UPDATE audit_log SET actor = 'nobody' WHERE id = :id"), {"id": first})
        db.session.commit()
        res = audit_chain.verify()
        assert not res["intact"] and res["first_bad_id"] == first and "changed" in res["problem"]
    finally:
        db.session.rollback()  # release this session's lock on audit_log before re-creating the triggers
        load_sql_objects(log=quiet, files=["06_audit_chain.sql"])


# --- 5. R9 follow-up actions ------------------------------------------------

def _r9_fraud():
    acc = make_account(avg=5000)
    db.session.add(SessionEvent(account_id=acc.id, device_id="SCAM-PHONE", ip_address="103.9.9.9", city="Delhi",
                                event_type="LOGIN", created_at=NOON - timedelta(minutes=5)))
    db.session.commit()
    payee = make_payee(acc, added_ago=timedelta(minutes=3), name="Kumar", account_no="88001234567")
    result = pay(acc, 15000, beneficiary_id=payee.id, device_id="SCAM-PHONE", ip_address="103.9.9.9",
                 channel="NETBANKING")
    assert "R9" in fired(result) and result["status"] != "APPROVED"
    return acc, payee, result


def test_r9_runs_step_up_cooling_off_alert_and_watchlisting():
    acc, payee, result = _r9_fraud()
    follow = result["r9_followup"]
    assert {(w["entry_type"], w["entry_value"]) for w in follow["watchlisted"]} == {
        ("DEVICE", "SCAM-PHONE"), ("IP", "103.9.9.9"), ("ACCOUNT", "88001234567")}
    db.session.expire_all()
    assert db.session.get(Beneficiary, payee.id).cooling_until == NOON + timedelta(hours=24)
    assert db.session.get(Account, acc.id).step_up_until == NOON + timedelta(hours=24)
    assert scalar("SELECT COUNT(*) FROM sessions WHERE device_id = 'SCAM-PHONE' AND is_active = 1") == 0
    channels = {r["channel"] for r in fetch_all(
        "SELECT channel FROM notifications WHERE ref_id = :id AND kind = 'ALERT'", {"id": result["txn_id"]})}
    assert channels == {"SMS", "APP"}  # the second, separate channel

    # Step-up: a new device must now be approved on the registered phone...
    other = make_payee(acc, name="Old Friend")
    res = otp_shield.request_otp(acc.id, other.id, 1000, "ANOTHER-PHONE", at=NOON + timedelta(hours=1))
    assert res["decision"] == "OTP_BLOCKED_APPROVAL_REQUIRED"
    assert "STEP_UP_REQUIRED" in {s["code"] for s in res["signals"]}
    # ...while the customer's own trusted phone is not slowed down by it.
    res = otp_shield.request_otp(acc.id, other.id, 1000, "DEV-T-1", at=NOON + timedelta(hours=1))
    assert "STEP_UP_REQUIRED" not in {s["code"] for s in res["signals"]}
    # The new payee is on its 24-hour cooling-off.
    with pytest.raises(AppError, match="24-hour"):
        otp_shield.request_otp(acc.id, payee.id, 1000, "DEV-T-1", at=NOON + timedelta(hours=1))


def test_r9_does_not_watchlist_the_customers_own_trusted_phone():
    acc = make_account(avg=5000)
    db.session.add(SessionEvent(account_id=acc.id, device_id="DEV-T-1", event_type="SIM_CHANGE",
                                created_at=NOON - timedelta(minutes=5)))
    db.session.commit()
    payee = make_payee(acc, added_ago=timedelta(hours=2), account_no="88009999999")
    result = pay(acc, 12000, beneficiary_id=payee.id, channel="NETBANKING")
    assert "R9" in fired(result)
    assert [w["entry_type"] for w in result["r9_followup"]["watchlisted"]] == ["ACCOUNT"]


def test_false_positive_lifts_the_r9_actions(client):
    acc, payee, result = _r9_fraud()
    case_id = Case.query.filter_by(alert_id=result["alert_id"]).one().id
    res = client.patch(f"/api/cases/{case_id}/outcome", json={"outcome": "FALSE_POSITIVE"},
                       headers=auth(staff_token(client, "analyst")))
    assert res.status_code == 200
    db.session.expire_all()
    assert scalar("SELECT COUNT(*) FROM watchlist WHERE added_by = 'r9-engine'") == 0
    assert db.session.get(Beneficiary, payee.id).cooling_until is None
    assert db.session.get(Account, acc.id).step_up_until is None


# --- 8. external model-score hook -------------------------------------------

def test_model_score_is_off_by_default():
    acc = make_account(avg=2000)
    result = pay(acc, 15000, model_score=90)  # R1 fires: 7.5x usual
    assert fired(result) == {"R1"} and result["risk_score"] == 40 and result["model_points"] is None


def test_model_score_adds_points_on_top_of_a_rule():
    _set("MODEL_SCORE_WEIGHT", 50)
    acc = make_account(avg=2000)
    result = pay(acc, 15000, model_score=80)
    assert result["model_points"] == 40 and result["risk_score"] == 80 and result["status"] == "BLOCKED"


def test_model_score_alone_never_flags_a_payment():
    _set("MODEL_SCORE_WEIGHT", 100)
    acc = make_account(avg=2000)
    result = pay(acc, 2100, model_score=100)
    assert result["status"] == "APPROVED" and result["risk_score"] == 0 and result["model_points"] is None


def test_model_score_is_validated(client):
    res = client.post("/api/transactions", headers={"X-API-Key": "dev-ingest-key"},
                      json={"external_ref": "M-1", "account_id": 1, "amount": 10, "channel": "UPI", "model_score": 150})
    assert res.status_code == 422


# --- 9. fraud rate by channel and city --------------------------------------

def test_dashboard_reports_confirmed_fraud_by_channel_and_city(client):
    acc = make_account(avg=2000)
    result = pay(acc, 15000, at=NOON + timedelta(days=1) - timedelta(hours=1), channel="CARD", city="Pune")
    case_id = Case.query.filter_by(alert_id=result["alert_id"]).one().id
    t = auth(staff_token(client, "analyst"))
    client.patch(f"/api/cases/{case_id}/outcome", json={"outcome": "CONFIRMED_FRAUD"}, headers=t)
    charts = client.get("/api/dashboard/charts?range=7d", headers=t).get_json()["data"]
    card = next(c for c in charts["by_channel"] if c["channel"] == "CARD")
    pune = next(c for c in charts["cities"] if c["city"] == "Pune")
    assert card["confirmed_fraud"] == 1 and pune["confirmed_fraud"] == 1
    summary = client.get("/api/dashboard/summary?range=7d", headers=t).get_json()["data"]
    assert summary["confirmed_fraud"] == 1 and summary["fraud_rate"] > 0


# --- 3. load test with and without the composite indexes ---------------------

def test_index_benchmark_compares_and_restores_indexes(client):
    seed_customers.run(log=quiet, count=30)
    seed_transactions.run(log=quiet, days=20, frauds_per_rule=0)
    simulator.clear_cache()
    result = index_benchmark.run(size=150, workers=4, seed=3, log=quiet)
    assert result["indexed"]["p95_ms"] > 0 and result["no_index"]["p95_ms"] > 0 and result["p95_speedup"]
    names = {r[0] for r in db.session.execute(text(
        "SELECT DISTINCT index_name FROM information_schema.statistics "
        "WHERE table_schema = DATABASE() AND table_name = 'transactions'"))}
    assert {"ix_txn_account_time", "ix_txn_account_city_time"} <= names and index_benchmark.STAND_IN not in names
    t = auth(staff_token(client, "risk"))
    pair = client.get("/api/evaluation/index-benchmark", headers=t).get_json()["data"]
    assert pair["indexed"]["run_id"] < pair["no_index"]["run_id"]
    assert client.get("/api/evaluation/latest", headers=t).get_json()["data"] is None  # benchmark runs kept apart


# --- R9: OTP typed from a new IP address -------------------------------------

def _otp_payment(acc, otp_id, verified_ip):
    payee = make_payee(acc, added_ago=timedelta(hours=1), account_no=f"7700{otp_id}")
    db.session.execute(text(
        "INSERT INTO otp_requests (id, account_id, beneficiary_id, amount, requesting_device_id, risk_points, "
        "decision, final_status, attempts, verified_at, verified_device_id, verified_ip, created_at) "
        "VALUES (:id, :a, :b, 12000, 'DEV-T-1', 25, 'OTP_SENT_WITH_WARNING', 'VERIFIED', 1, :t, 'DEV-T-1', :ip, :t)"
    ), {"id": otp_id, "a": acc.id, "b": payee.id, "t": NOON - timedelta(minutes=1), "ip": verified_ip})
    db.session.commit()
    return pay(acc, 12000, beneficiary_id=payee.id, otp_request_id=otp_id, channel="NETBANKING")


def test_r9_fires_when_otp_typed_from_a_new_ip_on_a_trusted_device():
    result = _otp_payment(make_account(avg=5000), 881, "185.77.1.2")
    assert "R9" in fired(result)
    hit = next(h for h in result["rules"] if h["rule_code"] == "R9")
    assert "185.77.1.2" in hit["detail_text"] and "internet address" in hit["detail_text"]


def test_r9_does_not_fire_for_otp_from_the_customers_usual_ip():
    assert "R9" not in fired(_otp_payment(make_account(avg=5000), 882, "49.1.1.1"))  # make_account's history IP


# --- latency to the COMMITTED decision ---------------------------------------

def test_latency_is_measured_to_the_committed_decision():
    result = pay(make_account(avg=2000), 2100)
    assert result["total_ms"] >= result["decision_ms"] > 0


# --- dashboard freshness, measured from the screen ---------------------------

def test_alert_freshness_is_measured_from_first_display(client):
    acc = make_account(avg=2000)
    result = pay(acc, 15000)  # R1 -> held, alert raised
    t = auth(staff_token(client, "analyst"))
    newest = client.get("/api/alerts", headers=t).get_json()["data"]["newest"]
    assert newest[0]["alert_id"] == result["alert_id"] and newest[0]["case_id"]
    # The alert was committed 1.5 s before the page shows it.
    db.session.execute(text("UPDATE alerts SET created_at = NOW(3) - INTERVAL 1500000 MICROSECOND "
                            "WHERE id = :id"), {"id": result["alert_id"]})
    db.session.commit()
    assert client.post("/api/alerts/seen", json={"alert_ids": [result["alert_id"]]}, headers=t).status_code == 200
    # A second report does not move the first-seen time.
    client.post("/api/alerts/seen", json={"alert_ids": [result["alert_id"]]}, headers=t)
    f = client.get("/api/alerts/freshness", headers=t).get_json()["data"]
    assert f["measured"] == 1 and 1400 <= f["p95_ms"] <= 3000 and f["pass"] is True


# --- load test against the API with and without indexes ----------------------

def test_index_benchmark_can_send_its_load_through_the_api(client):
    seed_customers.run(log=quiet, count=30)
    seed_transactions.run(log=quiet, days=20, frauds_per_rule=0)
    simulator.clear_cache()

    def submit(payload):  # the ingestion API, via the Flask test client
        body = {k: (v.isoformat() if hasattr(v, "isoformat") else float(v) if k == "amount" else v)
                for k, v in payload.items() if v is not None}
        res = client.post("/api/transactions", json=body, headers={"X-API-Key": "dev-ingest-key"})
        assert res.status_code in (200, 201), res.get_json()
        return res.get_json()["data"]

    result = index_benchmark.run(size=120, workers=1, seed=4, submit=submit, log=quiet)
    assert result["indexed"]["tps"] > 0 and result["no_index"]["tps"] > 0
    assert callable(evaluator.http_submitter("http://x/api", "k"))


# --- DDL script and Postman collection -----------------------------------------

DOCS = os.path.join(os.path.dirname(__file__), "..", "docs")


def test_schema_sql_matches_the_models():
    with open(schema_ddl.DDL_PATH, encoding="utf-8") as fh:
        assert fh.read() == schema_ddl.render(), "docs/schema.sql is out of date: run `flask export-ddl`"


def test_postman_collection_only_calls_real_routes(app):
    with open(os.path.join(DOCS, "FraudShield.postman_collection.json"), encoding="utf-8") as fh:
        collection = json.load(fh)
    routes = [(re.sub(r"<(?:\w+:)?\w+>", "[^/]+", r.rule), r.methods) for r in app.url_map.iter_rules()]
    requests_ = [i for folder in collection["item"] for i in folder["item"]]
    assert len(requests_) >= 40
    for item in requests_:
        raw = item["request"]["url"]["raw"].replace("{{baseUrl}}", "/api").replace("http://127.0.0.1:5000", "")
        path = re.sub(r"\{\{\w+\}\}", "1", raw.split("?")[0]).replace("%2B", "+")
        method = item["request"]["method"]
        assert any(re.fullmatch(rule, path) and method in methods for rule, methods in routes), (method, path)


# --- labelled dataset and the evaluation report (Table 3.1) -------------------

def test_evaluation_report_and_labelled_dataset(tmp_path):
    seed_customers.run(log=quiet, count=30)
    seed_transactions.run(log=quiet, days=20, frauds_per_rule=0)
    simulator.clear_cache()
    before = scalar("SELECT COUNT(*) FROM transactions")
    out = eval_report.run(size=150, bench_size=100, fraud_ratio=0.1, workers=4, seed=8, log=quiet,
                          path=str(tmp_path / "EVALUATION.md"), dataset_path=str(tmp_path / "data.csv"))
    m = out["metrics"]

    with open(tmp_path / "data.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert list(rows[0]) == dataset.COLUMNS and len(rows) == m["submitted"]
    assert {r["is_fraud_label"] for r in rows} <= {"0", "1", ""}
    assert sum(r["is_fraud_label"] == "1" for r in rows) == m["tp"] + m["fn"]
    combo = next(r for r in rows if r["scenario"] == "R1+R4" and r["is_fraud_label"] == "1")
    assert combo["expected_rules"] == "R1+R4" and {"R1", "R4"} <= set(combo["rules_fired"].split("+"))
    assert all(r["decision"] in ("APPROVED", "REVIEW", "BLOCKED") for r in rows)

    report = (tmp_path / "EVALUATION.md").read_text(encoding="utf-8")
    for row in ("End-to-end decision latency", "Sustained throughput", "Detection rate (recall)",
                "False-positive rate", "Explainability", "Dashboard freshness"):
        assert f"| {row}" in report, row
    assert "R5+R8" in report and "With indexes" in report and f"metric run #{m['run_id']}" in report
    assert scalar("SELECT COUNT(*) FROM transactions") == before  # the evaluation cleaned up after itself


def test_report_uses_measured_freshness_when_available():
    m = {"run_id": 1, "mode": "API", "submitted": 10, "total": 10, "fraud_ratio": 0.1, "p95_ms": 30.0, "p50_ms": 10.0,
         "tps": 150.0, "recall": 1.0, "tp": 1, "fn": 0, "fpr": 0.0, "fp": 0, "tn": 9, "explainability": 1.0,
         "explained": 1, "flagged": 1, "alert_visible_ms": 2100.0, "precision": 1.0, "f1": 1.0,
         "per_scenario": [], "per_rule": []}
    m["targets"] = evaluator.target_checks(m)
    fresh = {"measured": 4, "p95_ms": 2400.0, "max_ms": 2600.0, "pass": True}
    text_ = eval_report.render(m, None, fresh, [], {})
    assert "p95 2.40 s" in text_ and "4 alerts" in text_ and "✅ Pass" in text_
    assert "not yet measured" in eval_report.render(m, None, {"measured": 0}, [], {})
