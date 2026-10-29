"""Customer banking app, fraudster simulation console, and the money rules:
APPROVED debits, REVIEW holds, BLOCKED moves nothing; "This was me" pays a
held payment exactly once, "Not me" releases it and ends the fraudster's
session. Every simulated attack goes through fraud_engine.ingest and the
stored procedure."""

import uuid

import pytest

from portal.extensions import db
from portal.helpers.db_helpers import fetch_all, fetch_one, scalar
from portal.helpers.responses import AppError
from portal.seeders import seed_demo_users
from portal.services import attacker, fraud_engine
from tests.conftest import auth, make_account, pay, staff_token

VICTIM_PHONES = {"ravi": "RAVI-PIXEL-7", "priya": "PRIYA-IPHONE-14", "lakshmi": "LAKSHMI-REDMI-NOTE",
                 "suresh": "SURESH-GALAXY-A54", "arjun": "ARJUN-ONEPLUS-11"}


@pytest.fixture
def demo():
    seed_demo_users.run(log=lambda *_: None)


def headers(token=None, device="BROWSER-TEST-0001", city=None):
    h = {"X-Device-Id": device}
    if city:
        h["X-Demo-City"] = city
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def customer_login(client, username, device=None):
    device = device or VICTIM_PHONES[username]
    res = client.post("/api/customer/login", json={"username": username, "password": seed_demo_users.demo_password(username)},
                      headers=headers(device=device))
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]["token"]


def fraudster_login(client, username="hacker1", device="HACKER-LAPTOP-0001"):
    res = client.post("/api/attacker/login", json={"username": username, "password": "Hacker@123"},
                      headers=headers(device=device))
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]["token"]


def attack(client, token, code, device="HACKER-LAPTOP-0001"):
    res = client.post(f"/api/attacker/attack/{code}", headers=headers(token, device=device, city="Delhi"))
    assert res.status_code == 201, res.get_json()
    return res.get_json()["data"]


def account(username):
    return fetch_one("SELECT a.id, a.balance, a.held_amount, a.status FROM accounts a JOIN customer_users cu "
                     "ON cu.customer_id = a.customer_id WHERE cu.username = :u", {"u": username})


def target_step(result):
    return [s for s in result["steps"] if s.get("status") and s["attack"]][-1]


# --- seeding ---------------------------------------------------------------

def test_demo_seed_is_complete_and_repeatable(demo):
    seed_demo_users.run(log=lambda *_: None)  # second run adds nothing
    users = fetch_all("SELECT username, password_hash, card_last4 FROM customer_users ORDER BY username")
    assert [u["username"] for u in users] == ["arjun", "lakshmi", "priya", "ravi", "suresh"]
    assert all(u["password_hash"].startswith("$2") and "123" not in u["password_hash"] for u in users)
    assert all(u["card_last4"] for u in users)
    assert account("lakshmi")["status"] == "DORMANT"
    for username in ("priya", "suresh", "arjun"):
        acc = account(username)
        assert scalar("SELECT COUNT(*) FROM transactions WHERE account_id = :a AND source = 'SEED'", {"a": acc["id"]}) == 90
        assert scalar("SELECT COUNT(*) FROM beneficiaries WHERE account_id = :a", {"a": acc["id"]}) == 2
    assert scalar("SELECT COUNT(*) FROM fraudster_users") == 2
    assert scalar("SELECT COUNT(*) FROM stolen_credentials") == 8
    assert scalar("SELECT COUNT(*) FROM watchlist WHERE entry_type = 'ACCOUNT' AND entry_value = :v",
                  {"v": attacker.MULE["payee_account_no"]}) == 1


# --- authentication and isolation ------------------------------------------

def test_token_kinds_never_cross(client, demo):
    cust, fraud, staff = customer_login(client, "priya"), fraudster_login(client), staff_token(client)
    assert client.get("/api/alerts", headers=auth(cust)).status_code == 403
    assert client.get("/api/alerts", headers=auth(fraud)).status_code == 403
    assert client.get("/api/customer/me", headers=headers(fraud)).status_code == 401
    assert client.get("/api/customer/me", headers=headers(staff)).status_code == 401
    assert client.get("/api/attacker/me", headers=headers(cust)).status_code == 401
    assert client.get("/api/attacker/me", headers=headers(staff)).status_code == 401
    assert client.get("/api/customer/me", headers=headers(cust)).status_code == 200


def test_device_id_is_required_and_city_is_validated(client, demo):
    token = customer_login(client, "priya")
    assert client.get("/api/customer/me", headers=auth(token)).status_code == 400
    me = client.get("/api/customer/me", headers=headers(token, city="Atlantis")).get_json()["data"]
    assert me["device"]["city"] == "Bengaluru"  # unknown city ignored, home city used
    me = client.get("/api/customer/me", headers=headers(token, device="PRIYA-IPHONE-14", city="Delhi")).get_json()["data"]
    assert me["device"] == {"device_id": "PRIYA-IPHONE-14", "is_trusted": True, "city": "Delhi"}


def test_customer_sees_and_touches_only_own_data(client, demo):
    ravi, priya = customer_login(client, "ravi"), customer_login(client, "priya")
    ravi_payee = client.get("/api/customer/payees", headers=headers(ravi)).get_json()["data"][0]["id"]
    res = client.post("/api/customer/payments", headers=headers(priya, "PRIYA-IPHONE-14"),
                      json={"beneficiary_id": ravi_payee, "amount": 100, "idempotency_key": "k-other-0001"})
    assert res.status_code == 404
    fraud = fraudster_login(client)
    ravi_alert = target_step(attack(client, fraud, "R5"))  # hits ravi
    alert_id = scalar("SELECT id FROM customer_alerts WHERE txn_id = :t", {"t": ravi_alert["txn_id"]})
    assert client.post(f"/api/customer/alerts/{alert_id}/report", headers=headers(priya)).status_code == 404
    assert client.get("/api/customer/alerts", headers=headers(priya)).get_json()["data"]["items"] == []
    history = client.get("/api/customer/transactions", headers=headers(priya)).get_json()["data"]["items"]
    priya_acc = account("priya")["id"]
    assert all(scalar("SELECT account_id FROM transactions WHERE id = :i", {"i": t["id"]}) == priya_acc for t in history)


def test_customer_login_locks_after_five_wrong_passwords(client, demo):
    for _ in range(5):
        client.post("/api/customer/login", json={"username": "arjun", "password": "nope"}, headers=headers())
    res = client.post("/api/customer/login", json={"username": "arjun", "password": "Arjun@123"}, headers=headers())
    assert res.status_code == 423


def test_fraudster_sees_only_own_credentials_and_no_secrets(client, demo):
    me = client.get("/api/attacker/me", headers=headers(fraudster_login(client, "hacker2"))).get_json()["data"]
    assert {c["username"] for c in me["credentials"]} == {"arjun", "priya", "lakshmi", "suresh"}
    assert "hash" not in str(me).lower() and "Arjun@123" not in str(me)
    assert all(c["account"].startswith("XXXX") for c in me["credentials"])


def test_attacker_console_is_off_without_demo_mode(client, app, demo):
    app.config["DEMO_MODE"] = False
    try:
        assert client.post("/api/attacker/login", json={"username": "hacker1", "password": "Hacker@123"},
                           headers=headers()).status_code == 404
    finally:
        app.config["DEMO_MODE"] = True


# --- money rules -------------------------------------------------------------

def test_approved_payment_is_debited_once_even_if_retried(client, demo):
    token = customer_login(client, "priya")
    payee = client.get("/api/customer/payees", headers=headers(token)).get_json()["data"][0]["id"]
    before = account("priya")
    body = {"beneficiary_id": payee, "amount": 1500, "idempotency_key": "pay-once-0001"}
    first = client.post("/api/customer/payments", json=body, headers=headers(token, "PRIYA-IPHONE-14")).get_json()["data"]
    again = client.post("/api/customer/payments", json=body, headers=headers(token, "PRIYA-IPHONE-14")).get_json()["data"]
    assert first["status"] == "APPROVED" and first["funds_status"] == "DEBITED"
    assert again["txn_id"] == first["txn_id"] and again["duplicate"] is True
    assert float(account("priya")["balance"]) == float(before["balance"]) - 1500


def test_payment_beyond_available_balance_is_refused_and_not_saved(demo):
    acc = make_account(avg=2000)
    db.session.execute(db.text("UPDATE accounts SET balance = 100 WHERE id = :a"), {"a": acc.id})
    db.session.commit()
    before = scalar("SELECT COUNT(*) FROM transactions")
    with pytest.raises(AppError, match="Not enough"):
        pay(acc, 2000)
    assert scalar("SELECT COUNT(*) FROM transactions") == before  # rolled back with the decision


def test_review_holds_and_this_was_me_pays_exactly_once(client, demo):
    fraud = fraudster_login(client)
    step = target_step(attack(client, fraud, "R8"))  # lakshmi, dormant -> held for review
    assert step["status"] == "REVIEW" and step["funds_status"] == "HELD"
    acc = account("lakshmi")
    assert float(acc["held_amount"]) == step["amount"]

    token = customer_login(client, "lakshmi", device="LAKSHMI-NEW-TABLET")
    alerts = client.get("/api/customer/alerts", headers=headers(token, "LAKSHMI-NEW-TABLET")).get_json()["data"]
    alert = alerts["items"][0]
    assert alert["severity"] == "WARNING" and alert["action_status"] == "PENDING" and alerts["unread"] >= 1
    url = f"/api/customer/alerts/{alert['id']}/confirm"
    assert client.post(url, json={"password": "wrong"}, headers=headers(token, "LAKSHMI-NEW-TABLET")).status_code == 401
    res = client.post(url, json={"password": "Lakshmi@123"}, headers=headers(token, "LAKSHMI-NEW-TABLET")).get_json()["data"]
    assert res["paid"] is True
    assert client.post(url, json={"password": "Lakshmi@123"}, headers=headers(token, "LAKSHMI-NEW-TABLET")).status_code == 409
    after = account("lakshmi")
    assert float(after["held_amount"]) == 0
    assert float(after["balance"]) == float(acc["balance"]) - step["amount"]
    assert scalar("SELECT funds_status FROM transactions WHERE id = :t", {"t": step["txn_id"]}) == "PAID_AFTER_REVIEW"
    assert scalar("SELECT is_trusted FROM devices WHERE account_id = :a AND device_id = 'LAKSHMI-NEW-TABLET'",
                  {"a": acc["id"]}) == 1
    case = fetch_one("SELECT ca.customer_response FROM cases ca JOIN alerts al ON al.id = ca.alert_id WHERE al.txn_id = :t",
                     {"t": step["txn_id"]})
    assert case["customer_response"] == "CONFIRMED_ME"


def test_not_me_releases_hold_blocks_fraudster_and_marks_case(client, demo):
    fraud = fraudster_login(client)
    step = target_step(attack(client, fraud, "R8"))
    before = account("lakshmi")
    token = customer_login(client, "lakshmi")
    alert_id = client.get("/api/customer/alerts", headers=headers(token)).get_json()["data"]["items"][0]["id"]
    res = client.post(f"/api/customer/alerts/{alert_id}/report", headers=headers(token)).get_json()["data"]
    assert res["released"] and res["fraudster_logged_out"]
    after = account("lakshmi")
    assert float(after["held_amount"]) == 0 and float(after["balance"]) == float(before["balance"])  # nothing paid
    assert scalar("SELECT funds_status FROM transactions WHERE id = :t", {"t": step["txn_id"]}) == "RELEASED"
    assert scalar("SELECT COUNT(*) FROM watchlist WHERE entry_type = 'DEVICE' AND entry_value = 'HACKER-LAPTOP-0001'") == 1
    # The fraudster's open session is over...
    denied = client.get("/api/attacker/me", headers=headers(fraud))
    assert denied.status_code == 401 and denied.get_json()["error"]["code"] == "SESSION_REVOKED"
    # ...a repeated report changes nothing...
    assert client.post(f"/api/customer/alerts/{alert_id}/report", headers=headers(token)).status_code == 409
    # ...and staff see the customer's answer on the alert and the case.
    staff = auth(staff_token(client, "analyst"))
    queue = client.get("/api/alerts?status=ALL", headers=staff).get_json()["data"]["items"]
    row = next(r for r in queue if r["txn_id"] == step["txn_id"])
    assert row["customer_response"] == "REPORTED_NOT_ME" and row["funds_status"] == "RELEASED"
    case = client.get(f"/api/cases/{row['case_id']}", headers=staff).get_json()["data"]
    assert case["alert"]["customer_response"] == "REPORTED_NOT_ME"


def test_blocked_payment_moves_no_money(client, demo):
    before = account("suresh")
    step = target_step(attack(client, fraudster_login(client), "R6"))  # mule account -> R6 -> blocked
    assert step["status"] == "BLOCKED" and step["funds_status"] == "NOT_MOVED"
    after = account("suresh")
    assert after["balance"] == before["balance"] and after["held_amount"] == before["held_amount"]
    assert scalar("SELECT severity FROM customer_alerts WHERE txn_id = :t", {"t": step["txn_id"]}) == "DANGER"


# --- the simulation runs the real pipeline -------------------------------------

@pytest.mark.parametrize("code", ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9"])
def test_each_attack_fires_its_rule_through_the_stored_procedure(client, demo, code):
    result = attack(client, fraudster_login(client), code)
    assert result["expected_rules_fired"], result
    for s in result["steps"]:
        if s.get("status"):
            stored = fetch_one("SELECT status, risk_score, source FROM transactions WHERE id = :t", {"t": s["txn_id"]})
            hits = {r["rule_code"] for r in fetch_all("SELECT rule_code FROM rule_hits WHERE txn_id = :t",
                                                      {"t": s["txn_id"]})}
            # the decision shown is the one the stored procedure stored
            assert stored["status"] == s["status"] and stored["risk_score"] == s["risk_score"]
            assert hits == {h["rule_code"] for h in s["rules"]}
    if code == "R9":
        assert scalar("SELECT COUNT(*) FROM otp_requests") >= 1  # asked OTP Shield first
        assert any(s.get("otp_shield") for s in result["steps"])


def test_combined_attack_end_to_end(client, demo, monkeypatch):
    calls = []
    original = fraud_engine.ingest

    def spy(payload, source="API", t_received=None):
        calls.append(payload["external_ref"])
        return original(payload, source=source, t_received=t_received)

    monkeypatch.setattr(attacker.fraud_engine, "ingest", spy)
    result = attack(client, fraudster_login(client), "COMBINED")
    decided = [s for s in result["steps"] if s.get("status")]
    assert len(calls) == len(decided) >= 9  # every payment went through fraud_engine.ingest
    assert {"R3", "R2", "R6", "R9"} <= set(result["rules_fired"])
    assert result["bank_decision"] == "BLOCKED"
    victim = result["victim"]["username"]
    token = customer_login(client, victim)
    alerts = client.get("/api/customer/alerts", headers=headers(token)).get_json()["data"]["items"]
    assert len(alerts) >= 3 and {a["severity"] for a in alerts} >= {"WARNING", "DANGER"}
    # polling from the newest id returns nothing new -> no duplicate notifications
    newest = max(a["id"] for a in alerts)
    assert client.get(f"/api/customer/alerts?since_id={newest}", headers=headers(token)).get_json()["data"]["items"] == []
    events = client.get("/api/attacker/events", headers=headers(fraudster_login(client))).get_json()["data"]
    assert len(events) == len([s for s in decided if s["attack"]])


def test_demo_reset_restores_the_demo_accounts(client, demo):
    fraud = fraudster_login(client)
    attack(client, fraud, "R8")
    attack(client, fraud, "R1")
    res = client.post("/api/demo/reset", headers=headers(fraud)).get_json()["data"]
    assert set(res["reset"]) == {"ravi", "priya", "suresh", "lakshmi", "arjun"} and res["payments_removed"] >= 2
    lakshmi = account("lakshmi")
    assert float(lakshmi["held_amount"]) == 0 and float(lakshmi["balance"]) == 260000 and lakshmi["status"] == "DORMANT"
    assert scalar("SELECT COUNT(*) FROM customer_alerts") == 0
    assert scalar("SELECT COUNT(*) FROM transactions WHERE source = 'ATTACK_SIM'") == 0
    assert scalar("SELECT COUNT(*) FROM watchlist WHERE entry_value = :v",
                  {"v": attacker.MULE["payee_account_no"]}) == 1  # seeded mule entry kept


def test_ingest_still_works_for_ordinary_accounts():
    # Untouched path: an ordinary API payment is still decided by the procedure and debited.
    acc = make_account(avg=2000)
    res = pay(acc, 2100, external_ref=f"ORD-{uuid.uuid4().hex[:8]}")
    assert res["status"] == "APPROVED" and res["funds_status"] == "DEBITED"
