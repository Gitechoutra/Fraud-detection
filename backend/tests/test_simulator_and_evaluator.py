"""Every fraud story fires its own rule; evaluation computes metrics and
cleans up after itself; the live stream starts and stops."""

import time

import pytest

from portal.extensions import db
from portal.helpers.db_helpers import scalar
from portal.models import MetricRun
from portal.seeders import seed_customers, seed_demo_story, seed_transactions
from portal.services import evaluator, simulator
from tests.conftest import auth, quiet, staff_token


@pytest.fixture
def population():
    seed_customers.run(log=quiet, count=40)
    seed_demo_story.run(log=quiet)
    seed_transactions.run(log=quiet, days=30, frauds_per_rule=0)
    simulator.clear_cache()


@pytest.mark.parametrize("code", ["NORMAL"] + simulator.RULE_CODES)
def test_each_scenario_triggers_its_rule(population, code):
    result = simulator.run_scenario(code)
    assert result["expected_rule_fired"], result["summary"]
    if code == "NORMAL":
        assert result["target"]["status"] == "APPROVED"
    else:
        assert code in {h["rule_code"] for h in result["target"]["rules"]}


def test_scenarios_over_the_api(client, population):
    t = auth(staff_token(client, "risk"))
    assert len(client.get("/api/simulator/scenarios", headers=t).get_json()["data"]) == 10
    res = client.post("/api/simulator/scenario/R3", headers=t).get_json()["data"]
    assert res["expected_rule"] == "R3" and res["expected_rule_fired"]
    assert len(res["steps"]) == 2
    assert client.post("/api/simulator/scenario/R42", headers=t).status_code == 404


def test_evaluation_metrics_and_cleanup(population):
    before = scalar("SELECT COUNT(*) FROM transactions")
    m = evaluator.run_evaluation(size=200, fraud_ratio=0.1, days=7, workers=4, seed=11)
    assert m["total"] >= 200
    assert m["tp"] + m["fn"] >= 18  # 10% fraud, at least 2 per rule
    assert 0 <= m["fpr"] <= 1 and 0 <= m["recall"] <= 1
    assert len(m["per_rule"]) == 9 and len(m["per_scenario"]) == 9
    assert all(s["rule_fired"] == s["count"] for s in m["per_scenario"])  # every story fired its rule
    assert m["p95_ms"] > 0 and m["tps"] > 0
    assert set(m["targets"]) == {"recall", "fpr", "p95_ms", "tps"}
    run = db.session.get(MetricRun, m["run_id"])
    assert run.total == m["total"]
    # Everything the evaluation created is gone again.
    assert scalar("SELECT COUNT(*) FROM transactions") == before
    assert scalar("SELECT COUNT(*) FROM transactions WHERE source = 'EVALUATION'") == 0
    assert scalar("SELECT COUNT(*) FROM otp_requests") == 0


def test_evaluation_api_history(client, population):
    evaluator.run_evaluation(size=100, fraud_ratio=0.1, workers=2, seed=5)
    t = auth(staff_token(client, "risk"))
    latest = client.get("/api/evaluation/latest", headers=t).get_json()["data"]
    assert latest["targets"]["recall"]["target"] == 0.9
    history = client.get("/api/evaluation/history", headers=t).get_json()["data"]
    assert len(history["runs"]) == 1
    assert client.get("/api/evaluation/status", headers=t).get_json()["data"]["running"] is False


def test_live_stream_start_stop(client, population, app):
    t = auth(staff_token(client, "risk"))
    started = client.post("/api/simulator/stream/start", json={"rate": 5, "fraud_ratio": 0.0}, headers=t)
    assert started.get_json()["data"]["running"] is True
    deadline = time.time() + 10
    while simulator.STREAM.stats["sent"] < 3 and time.time() < deadline:
        time.sleep(0.2)
    stopped = client.post("/api/simulator/stream/stop", headers=t).get_json()["data"]
    assert stopped["running"] is False and stopped["sent"] >= 3 and stopped["errors"] == 0
    db.session.rollback()  # end this session's snapshot so the stream thread's commits are visible
    assert scalar("SELECT COUNT(*) FROM transactions WHERE source = 'SIMULATOR'") >= 3
