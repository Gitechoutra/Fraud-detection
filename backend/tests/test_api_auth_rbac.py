"""Login, token refresh, logout, role checks, and a pass over every staff API."""

from datetime import timedelta

from portal.helpers.db_helpers import scalar
from tests.conftest import NOON, auth, make_account, pay, staff_token


# --- auth -----------------------------------------------------------------

def test_login_success_and_me(client):
    res = client.post("/api/auth/login", json={"username": "analyst", "password": "Analyst@123"})
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert data["user"]["role"] == "ANALYST" and data["access_token"] and data["refresh_token"]
    me = client.get("/api/auth/me", headers=auth(data["access_token"]))
    assert me.get_json()["data"]["username"] == "analyst"
    assert scalar("SELECT COUNT(*) FROM audit_log WHERE action = 'LOGIN'") == 1


def test_login_wrong_password(client):
    res = client.post("/api/auth/login", json={"username": "admin", "password": "nope"})
    assert res.status_code == 401
    assert res.get_json() == {"ok": False, "error": {"code": "INVALID_CREDENTIALS",
                                                     "message": "Wrong username or password."}}


def test_login_validation(client):
    assert client.post("/api/auth/login", json={}).status_code == 422


def test_refresh_gives_new_access_token(client):
    data = client.post("/api/auth/login", json={"username": "risk", "password": "Risk@123"}).get_json()["data"]
    res = client.post("/api/auth/refresh", headers=auth(data["refresh_token"]))
    assert res.status_code == 200
    new_token = res.get_json()["data"]["access_token"]
    assert client.get("/api/auth/me", headers=auth(new_token)).status_code == 200
    # An access token can't be used to refresh.
    assert client.post("/api/auth/refresh", headers=auth(data["access_token"])).status_code == 401


def test_logout_revokes_access_and_refresh(client):
    data = client.post("/api/auth/login", json={"username": "admin", "password": "Admin@123"}).get_json()["data"]
    res = client.post("/api/auth/logout", json={"refresh_token": data["refresh_token"]},
                      headers=auth(data["access_token"]))
    assert res.status_code == 200
    me = client.get("/api/auth/me", headers=auth(data["access_token"]))
    assert me.status_code == 401 and me.get_json()["error"]["code"] == "TOKEN_REVOKED"
    assert client.post("/api/auth/refresh", headers=auth(data["refresh_token"])).status_code == 401


def test_missing_and_garbage_tokens(client):
    assert client.get("/api/dashboard/summary").get_json()["error"]["code"] == "UNAUTHORIZED"
    res = client.get("/api/dashboard/summary", headers=auth("not.a.token"))
    assert res.status_code == 422 or res.status_code == 401


def test_disabled_user_cannot_log_in(client):
    admin = staff_token(client)
    created = client.post("/api/users", json={"username": "temp_user", "full_name": "Temp User",
                                              "password": "Password1!", "role": "ANALYST"}, headers=auth(admin))
    uid = created.get_json()["data"]["id"]
    client.patch(f"/api/users/{uid}", json={"is_active": False}, headers=auth(admin))
    res = client.post("/api/auth/login", json={"username": "temp_user", "password": "Password1!"})
    assert res.status_code == 403


# --- role checks ------------------------------------------------------------

def test_analyst_permissions(client):
    t = auth(staff_token(client, "analyst", "Analyst@123"))
    assert client.get("/api/rules", headers=t).status_code == 200
    assert client.put("/api/rules/R2", json={"weight": 30}, headers=t).status_code == 403
    assert client.post("/api/watchlist", json={"entry_type": "IP", "entry_value": "1.2.3.4", "reason": "test"},
                       headers=t).status_code == 403
    assert client.get("/api/audit", headers=t).status_code == 403
    assert client.get("/api/users", headers=t).status_code == 403
    assert client.post("/api/simulator/scenario/R1", headers=t).status_code == 403
    assert client.get("/api/evaluation/history", headers=t).status_code == 403


def test_risk_manager_permissions(client):
    t = auth(staff_token(client, "risk", "Risk@123"))
    res = client.put("/api/rules/R2", json={"param_1": 7, "weight": 30}, headers=t)
    assert res.status_code == 200 and res.get_json()["data"]["params"][0] == 7.0
    assert client.get("/api/audit", headers=t).status_code == 200
    assert client.get("/api/users", headers=t).status_code == 403
    # The DB trigger recorded the rule change with the user's name.
    assert scalar("SELECT actor FROM audit_log WHERE action = 'RULE_UPDATED' AND entity_id = 'R2'") == "risk"


def test_admin_user_management(client):
    t = auth(staff_token(client))
    res = client.post("/api/users", json={"username": "priya", "full_name": "Priya Sharma",
                                          "password": "Priya@12345", "role": "ANALYST"}, headers=t)
    assert res.status_code == 201
    uid = res.get_json()["data"]["id"]
    assert client.post("/api/users", json={"username": "priya", "full_name": "Dup", "password": "Priya@12345",
                                           "role": "ANALYST"}, headers=t).status_code == 409
    upd = client.patch(f"/api/users/{uid}", json={"role": "RISK_MANAGER"}, headers=t)
    assert upd.get_json()["data"]["role"] == "RISK_MANAGER"
    me = client.get("/api/auth/me", headers=t).get_json()["data"]
    assert client.patch(f"/api/users/{me['id']}", json={"is_active": False}, headers=t).status_code == 400
    assert len(client.get("/api/users", headers=t).get_json()["data"]) == 4


# --- every staff API --------------------------------------------------------

def _flagged_payment():
    acc = make_account(avg=2000, history=10)
    return acc, pay(acc, 30000, device_id="DEV-STOLEN-0001")  # R1 + R4 + R6 -> blocked


def test_transactions_list_latest_detail(client):
    acc, result = _flagged_payment()
    pay(acc, 300, at=NOON + timedelta(minutes=30))
    t = auth(staff_token(client, "analyst", "Analyst@123"))
    listed = client.get("/api/transactions?status=BLOCKED&per_page=5", headers=t).get_json()["data"]
    assert listed["total"] >= 1 and listed["items"][0]["status"] == "BLOCKED"
    assert "R6" in listed["items"][0]["rule_codes"]
    search = client.get(f"/api/transactions?search={acc.account_no}", headers=t).get_json()["data"]
    assert search["total"] == 12
    latest = client.get(f"/api/transactions/latest?since_id={result['txn_id']}", headers=t).get_json()["data"]
    assert len(latest["items"]) == 1 and latest["items"][0]["amount"] == 300.0
    detail = client.get(f"/api/transactions/{result['txn_id']}", headers=t).get_json()["data"]
    assert detail["transaction"]["status"] == "BLOCKED"
    assert len(detail["rules"]) == 9 and sum(r["fired"] for r in detail["rules"]) == 3
    assert detail["explanation"]["headline"].startswith("This payment was stopped")
    assert detail["alert"]["case_id"] and len(detail["history"]) > 1
    assert client.get("/api/transactions/999999", headers=t).status_code == 404


def test_alerts_and_cases_workflow(client):
    _, result = _flagged_payment()
    t = auth(staff_token(client, "analyst", "Analyst@123"))
    alerts = client.get("/api/alerts?status=OPEN", headers=t).get_json()["data"]
    assert alerts["counts"]["OPEN"] == 1
    alert = alerts["items"][0]
    assert alert["txn_id"] == result["txn_id"] and alert["priority"] == "HIGH"
    mine = client.patch(f"/api/alerts/{alert['alert_id']}", json={"assign_to_me": True}, headers=t).get_json()["data"]
    assert mine["alert_status"] == "IN_PROGRESS" and mine["assigned_name"] == "Anita Analyst"

    case_id = alert["case_id"]
    note = client.post(f"/api/cases/{case_id}/notes", json={"body": "Called customer, no answer."}, headers=t)
    assert note.status_code == 201
    case = client.get(f"/api/cases/{case_id}", headers=t).get_json()["data"]
    assert len(case["hits"]) == 3 and len(case["notes"]) == 1 and case["timeline"]
    closed = client.patch(f"/api/cases/{case_id}/outcome", json={"outcome": "CONFIRMED_FRAUD",
                                                                  "notes": "Customer confirmed fraud."}, headers=t)
    assert closed.status_code == 200
    assert client.patch(f"/api/cases/{case_id}/outcome", json={"outcome": "FALSE_POSITIVE"},
                        headers=t).status_code == 409
    assert scalar("SELECT alert_status FROM alerts WHERE id = :id", {"id": alert["alert_id"]}) == "CLOSED"
    assert scalar("SELECT COUNT(*) FROM audit_log WHERE action = 'CASE_CLOSED'") == 1
    precision = {r["rule_code"]: r for r in client.get("/api/rules", headers=t).get_json()["data"]["rules"]}
    assert precision["R6"]["stats"]["confirmed_fraud"] == 1


def test_rules_and_bands(client):
    t = auth(staff_token(client, "risk", "Risk@123"))
    data = client.get("/api/rules", headers=t).get_json()["data"]
    assert len(data["rules"]) == 9 and data["bands"] == {"review_threshold": 40, "block_threshold": 70}
    assert client.put("/api/rules/R1", json={"is_active": False}, headers=t).get_json()["data"]["is_active"] is False
    assert client.put("/api/rules/ZZ", json={"weight": 1}, headers=t).status_code == 404
    assert client.put("/api/rules/bands", json={"review_threshold": 70, "block_threshold": 40},
                      headers=t).status_code == 422
    res = client.put("/api/rules/bands", json={"review_threshold": 35, "block_threshold": 75}, headers=t)
    assert res.get_json()["data"] == {"review_threshold": 35, "block_threshold": 75}
    assert len(client.get("/api/rules", headers=t).get_json()["data"]["history"]) == 2


def test_watchlist_crud(client):
    t = auth(staff_token(client, "risk", "Risk@123"))
    res = client.post("/api/watchlist", json={"entry_type": "IP", "entry_value": "9.9.9.9", "reason": "Test entry"},
                      headers=t)
    assert res.status_code == 201
    entry_id = res.get_json()["data"]["id"]
    assert client.post("/api/watchlist", json={"entry_type": "IP", "entry_value": "9.9.9.9", "reason": "Again"},
                       headers=t).status_code == 409
    found = client.get("/api/watchlist?search=9.9.9", headers=t).get_json()["data"]
    assert found["total"] == 1
    assert client.delete(f"/api/watchlist/{entry_id}", headers=t).status_code == 200
    assert scalar("SELECT COUNT(*) FROM audit_log WHERE entity = 'watchlist'") == 2  # trigger: add + remove


def test_dashboard_customers_audit(client):
    _flagged_payment()
    t = auth(staff_token(client))
    summary = client.get("/api/dashboard/summary?range=7d", headers=t).get_json()["data"]
    assert summary["blocked"] == 1 and summary["money_protected"] == 30000.0
    charts = client.get("/api/dashboard/charts?range=7d", headers=t).get_json()["data"]
    assert set(charts) >= {"volume", "decisions", "by_channel", "cities", "rule_hits", "rule_precision"}
    assert client.get("/api/dashboard/charts?range=today", headers=t).status_code == 200
    assert client.get("/api/dashboard/summary?range=1y", headers=t).status_code == 400
    customers = client.get("/api/customers?search=Test", headers=t).get_json()["data"]
    assert customers["total"] == 1
    detail = client.get(f"/api/customers/{customers['items'][0]['id']}", headers=t).get_json()["data"]
    assert detail["accounts"] and detail["devices"] and detail["recent_transactions"]
    assert client.get("/api/customers/999999", headers=t).status_code == 404
    assert client.get("/api/audit", headers=t).get_json()["data"]["total"] >= 1


def test_health_and_index(client):
    assert client.get("/health").get_json()["data"]["procedures"] == 2
    assert client.get("/").get_json()["data"]["name"] == "FraudShield API"
    assert client.get("/api/nope").status_code == 404
