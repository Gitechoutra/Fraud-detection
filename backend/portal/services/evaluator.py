"""
portal/services/evaluator.py
============================
Measures how good the rules are on a fresh, labelled synthetic data set.

1. Builds `size` labelled payments: (1 - fraud_ratio) normal, the rest
   spread evenly over the fraud stories -- one per rule plus the
   rule-combination stories (simulator.COMBOS) -- at random times over the
   last `days` days (so velocity rules see realistic spacing).
2. Runs them through the real engine -- in-process, or over HTTP when a
   `submit` function is given (evaluate.py --api-url) -- with several
   workers in parallel. A story's own payments stay in order.
3. Computes the confusion matrix (positive = REVIEW or BLOCKED), precision,
   recall, F1, false-positive rate, p50/p95 latency (request receipt to
   committed decision) and throughput,
   explainability (share of flagged payments that list their rules) and
   alert visibility (worst-case time until a new alert is on screen), plus
   per-rule precision and per-story recall. Saves a metric_runs row.
4. Deletes everything it created (unless keep=True), so evaluation never
   pollutes the dashboard, alert queue or customers' history.
"""

import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from decimal import Decimal

import requests

from flask import current_app
from sqlalchemy import text

from portal.extensions import db
from portal.helpers.timing import percentile
from portal.models import MetricRun
from portal.services import simulator

TARGETS = {"recall": 0.90, "fpr": 0.05, "p95_ms": 500.0, "tps": 100.0, "explainability": 1.0,
           "alert_visible_ms": 3000.0}

# How often the Alerts page and Live Monitor re-read the queue
# (frontend/src/utils/polling.js ALERT_POLL_MS -- keep the two equal).
ALERT_POLL_MS = 2000

# Progress of the evaluation currently running in this process (for the UI).
PROGRESS = {"running": False, "done": 0, "total": 0, "started_at": None, "last_run_id": None, "error": None}
_progress_lock = threading.Lock()


_local = threading.local()


def http_submitter(api_url, api_key):
    """A submit function that POSTs each payment to the ingestion API (the
    load-generation path used by evaluate.py, simulate.py and the index
    benchmark). One HTTP session per worker thread."""
    def submit(payload):
        session = getattr(_local, "session", None)
        if session is None:
            session = _local.session = requests.Session()
        body = {
            k: (v.isoformat() if isinstance(v, datetime) else float(v) if isinstance(v, Decimal) else v)
            for k, v in payload.items()
            if v is not None
        }
        res = session.post(f"{api_url}/transactions", json=body, headers={"X-API-Key": api_key}, timeout=30)
        if res.status_code not in (200, 201):
            raise RuntimeError(f"API {res.status_code}: {res.text[:200]}")
        return res.json()["data"]

    return submit


def api_reachable(api_url):
    try:
        return requests.get(api_url.rsplit("/api", 1)[0] + "/health", timeout=3).ok
    except requests.RequestException:
        return False


def _set_progress(**kwargs):
    with _progress_lock:
        PROGRESS.update(kwargs)


def _bump():
    with _progress_lock:
        PROGRESS["done"] += 1


def _build_tasks(size, fraud_ratio, days, rng):
    stories = simulator.FRAUD_SCENARIOS
    n_fraud = max(len(stories), round(size * fraud_ratio))
    n_normal = max(0, size - n_fraud)
    codes = [stories[i % len(stories)] for i in range(n_fraud)]
    tasks = ["NORMAL"] * n_normal + codes
    rng.shuffle(tasks)
    now = datetime.now()
    return [(code, now - timedelta(seconds=rng.uniform(0, days * 86400))) for code in tasks]


def _run_task(app, code, base_time, seed, submit):
    with app.app_context():
        ctx = simulator.ScenarioContext(
            source="EVALUATION", base_time=base_time, live=False,
            rng=random.Random(seed), submit=submit, prefix="EVAL",
        )
        try:
            simulator.SCENARIOS[code](ctx)
        except Exception:
            db.session.rollback()
            app.logger.exception("Evaluation task %s failed", code)
            ctx.created["failed"].append(code)
        finally:
            db.session.remove()
        _bump()
        return ctx


def _metrics(results):
    labelled = [r for r in results if r["label"] is not None]
    tp = sum(1 for r in labelled if r["label"] == 1 and r["flagged"])
    fn = sum(1 for r in labelled if r["label"] == 1 and not r["flagged"])
    fp = sum(1 for r in labelled if r["label"] == 0 and r["flagged"])
    tn = sum(1 for r in labelled if r["label"] == 0 and not r["flagged"])
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    fpr = fp / (fp + tn) if fp + tn else 0.0

    per_rule = []
    for code in simulator.RULE_CODES:
        hits = [r for r in labelled if code in r["rules"]]
        true_hits = sum(1 for r in hits if r["label"] == 1)
        per_rule.append({
            "rule_code": code,
            "hits": len(hits),
            "true_hits": true_hits,
            "precision": round(true_hits / len(hits), 4) if hits else None,
        })
    per_scenario = []
    for code in simulator.FRAUD_SCENARIOS:
        expected = simulator.expected_rules(code)
        targets = [r for r in labelled if r["scenario"] == code and r["label"] == 1]
        caught = sum(1 for r in targets if r["flagged"])
        rule_fired = sum(1 for r in targets if all(c in r["rules"] for c in expected))
        per_scenario.append({
            "scenario": code,
            "count": len(targets),
            "caught": caught,
            "recall": round(caught / len(targets), 4) if targets else None,
            "rule_fired": rule_fired,
            "rules": expected,
        })
    flagged = [r for r in results if r["flagged"]]
    explained = sum(1 for r in flagged if r["rules"])
    return {
        "total": len(labelled), "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "precision": precision, "recall": recall, "f1": f1, "fpr": fpr,
        "flagged": len(flagged), "explained": explained,
        "explainability": explained / len(flagged) if flagged else 1.0,
        "per_rule": per_rule, "per_scenario": per_scenario,
    }


def _chunks(seq, n=500):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def snapshot_accounts():
    """{account_id: (last_txn_at, status)} -- taken before a run so cleanup
    can restore the accounts exactly."""
    return {r[0]: (r[1], r[2]) for r in db.session.execute(text("SELECT id, last_txn_at, status FROM accounts"))}


def cleanup(created, accounts_before, started_at):
    """Removes every row an evaluation created and restores the accounts it
    touched to their state before the run (`accounts_before`, from
    snapshot_accounts at `started_at`)."""
    params_list = lambda ids: {f"p{i}": v for i, v in enumerate(ids)}  # noqa: E731
    placeholders = lambda ids: ", ".join(f":p{i}" for i in range(len(ids)))  # noqa: E731

    def delete(sql_template, ids):
        for chunk in _chunks(ids):
            db.session.execute(text(sql_template.format(ids=placeholders(chunk))), params_list(chunk))

    approval_ids = []
    for chunk in _chunks(created["otp_requests"]):
        approval_ids += [
            r[0] for r in db.session.execute(
                text(f"SELECT id FROM device_approvals WHERE otp_request_id IN ({placeholders(chunk)})"),
                params_list(chunk),
            )
        ]
    delete("DELETE FROM notifications WHERE kind = 'APPROVAL' AND ref_id IN ({ids})", approval_ids)
    delete("DELETE FROM notifications WHERE kind = 'OTP' AND ref_id IN ({ids})", created["otp_requests"])
    delete("DELETE FROM transactions WHERE id IN ({ids})", created["txn_ids"])  # cascades hits/alerts/cases
    delete("DELETE FROM otp_requests WHERE id IN ({ids})", created["otp_requests"])  # cascades approvals
    delete("DELETE FROM sessions WHERE id IN ({ids})", created["sessions"])
    delete("DELETE FROM beneficiaries WHERE id IN ({ids})", created["beneficiaries"])
    delete("DELETE FROM devices WHERE device_id IN ({ids})", created["devices"])
    # Put each touched account back exactly as it was before the run (an
    # approved test payment moved last_txn_at forward and may have woken a
    # dormant account). Real payments approved meanwhile still count.
    for account_id in sorted(set(created["accounts"])):
        if account_id not in accounts_before:
            continue
        last_txn_at, status = accounts_before[account_id]
        newer = db.session.execute(
            text("SELECT MAX(txn_time) FROM transactions "
                 "WHERE account_id = :id AND status = 'APPROVED' AND created_at >= :started"),
            {"id": account_id, "started": started_at},
        ).scalar()
        if newer and (last_txn_at is None or newer > last_txn_at):
            last_txn_at, status = newer, "ACTIVE" if status == "DORMANT" else status
        db.session.execute(text("UPDATE accounts SET last_txn_at = :last, status = :status WHERE id = :id"),
                           {"last": last_txn_at, "status": status, "id": account_id})
    db.session.commit()


def _alert_queue_read_ms(samples=5):
    """Median time of the query behind the Alerts page (newest open alerts)."""
    times = []
    for _ in range(samples):
        t0 = time.perf_counter()
        db.session.execute(text("SELECT * FROM v_alert_queue ORDER BY created_at DESC LIMIT 25")).fetchall()
        times.append((time.perf_counter() - t0) * 1000)
    return percentile(times, 50)


def measured_alert_freshness(days=7):
    """Measured time from an alert being committed to the Alerts page first
    showing it (alerts.first_seen_at, both stamped by the database clock)
    over the last `days` days -- Table 3.1's "timestamp comparison between
    commit and UI display"."""
    lags = [float(r[0]) for r in db.session.execute(text(
        "SELECT TIMESTAMPDIFF(MICROSECOND, created_at, first_seen_at) / 1000 FROM alerts "
        "WHERE first_seen_at IS NOT NULL AND created_at >= NOW() - INTERVAL :d DAY"), {"d": days})]
    p95 = round(percentile(lags, 95), 1) if lags else None
    return {
        "days": days,
        "measured": len(lags),
        "p50_ms": round(percentile(lags, 50), 1) if lags else None,
        "p95_ms": p95,
        "max_ms": round(max(lags), 1) if lags else None,
        "target_ms": TARGETS["alert_visible_ms"],
        "pass": p95 is not None and p95 <= TARGETS["alert_visible_ms"],
    }


def run_evaluation(size=5000, fraud_ratio=0.03, days=7, workers=8, submit=None, mode="IN_PROCESS",
                   keep=False, seed=None, log=None, with_rows=False):
    """Returns the metrics; with_rows=True adds m["rows"], one dict per
    submitted payment with its label and decision (services/dataset.py)."""
    app = current_app._get_current_object()
    log = log or app.logger.info
    rng = random.Random(seed)
    simulator.get_cache(force=True)
    started_at = datetime.now()
    accounts_before = snapshot_accounts()
    db.session.commit()
    tasks = _build_tasks(size, fraud_ratio, days, rng)
    _set_progress(running=True, done=0, total=len(tasks), started_at=datetime.now().isoformat(), error=None)
    log(f"Evaluating {len(tasks)} labelled payments ({fraud_ratio:.1%} fraud) with {workers} workers [{mode}]")

    contexts = []
    t0 = time.perf_counter()
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(_run_task, app, code, base, rng.randint(0, 10**9), submit)
                for code, base in tasks
            ]
            for f in as_completed(futures):
                contexts.append(f.result())
        wall = time.perf_counter() - t0

        results, created = [], {k: [] for k in
                                ("txn_ids", "sessions", "beneficiaries", "otp_requests", "devices", "accounts")}
        failed = 0
        for ctx in contexts:
            failed += len(ctx.created.get("failed", []))
            for k in created:
                created[k].extend(ctx.created.get(k, []))
            for r in ctx.results:
                res = r["result"]
                results.append({
                    "label": r["label"],
                    "scenario": r["scenario"],
                    "flagged": res["status"] in ("REVIEW", "BLOCKED"),
                    "rules": [h["rule_code"] for h in res["rules"]],
                    # receipt -> committed decision (total_ms); a duplicate
                    # only has the stored pre-commit time
                    "decision_ms": res.get("total_ms") or res["decision_ms"] or 0.0,
                    "payload": r["payload"],
                    "status": res["status"],
                    "risk_score": res["risk_score"],
                })

        latencies = [r["decision_ms"] for r in results]
        m = _metrics(results)
        m.update(
            p50_ms=round(percentile(latencies, 50), 2),
            p95_ms=round(percentile(latencies, 95), 2),
            tps=round(len(results) / wall, 2) if wall else 0.0,
            # A flagged payment's alert is committed with its decision, so it
            # is on screen at the latest one polling interval later.
            alert_visible_ms=round(percentile(latencies, 95) + _alert_queue_read_ms() + ALERT_POLL_MS, 2),
            submitted=len(results),
            failed_tasks=failed,
            wall_seconds=round(wall, 2),
        )
        run = MetricRun(
            run_at=datetime.now(), total=m["total"], tp=m["tp"], fp=m["fp"], tn=m["tn"], fn=m["fn"],
            precision_v=round(m["precision"], 4), recall_v=round(m["recall"], 4), f1=round(m["f1"], 4),
            fpr=round(m["fpr"], 4), p50_ms=m["p50_ms"], p95_ms=m["p95_ms"], tps=m["tps"],
            explainability=round(m["explainability"], 4), alert_visible_ms=m["alert_visible_ms"],
            fraud_ratio=fraud_ratio, mode=mode, per_rule_json=m["per_rule"], per_scenario_json=m["per_scenario"],
        )
        db.session.add(run)
        db.session.commit()
        m["run_id"] = run.id
        m["targets"] = target_checks(m)
        m["mode"], m["fraud_ratio"], m["run_at"] = mode, fraud_ratio, run.run_at.isoformat()
        if with_rows:
            m["rows"] = results
        if not keep:
            cleanup(created, accounts_before, started_at)
            simulator.get_cache(force=True)
        _set_progress(running=False, last_run_id=run.id)
        log(
            f"Done in {wall:.1f}s: recall {m['recall']:.1%}, FPR {m['fpr']:.2%}, "
            f"precision {m['precision']:.1%}, p95 {m['p95_ms']} ms, {m['tps']} TPS, "
            f"explained {m['explainability']:.1%}, alert on screen within {m['alert_visible_ms']:.0f} ms"
        )
        return m
    except Exception as exc:
        _set_progress(running=False, error=str(exc))
        raise


def target_checks(m):
    checks = {
        "recall": {"target": TARGETS["recall"], "value": m["recall"], "pass": m["recall"] >= TARGETS["recall"]},
        "fpr": {"target": TARGETS["fpr"], "value": m["fpr"], "pass": m["fpr"] <= TARGETS["fpr"]},
        "p95_ms": {"target": TARGETS["p95_ms"], "value": m["p95_ms"], "pass": m["p95_ms"] <= TARGETS["p95_ms"]},
        "tps": {"target": TARGETS["tps"], "value": m["tps"], "pass": m["tps"] >= TARGETS["tps"]},
    }
    # Older runs were saved before these two were measured.
    if m.get("explainability") is not None:
        checks["explainability"] = {"target": TARGETS["explainability"], "value": m["explainability"],
                                    "pass": m["explainability"] >= TARGETS["explainability"]}
    if m.get("alert_visible_ms") is not None:
        checks["alert_visible_ms"] = {"target": TARGETS["alert_visible_ms"], "value": m["alert_visible_ms"],
                                      "pass": m["alert_visible_ms"] <= TARGETS["alert_visible_ms"]}
    return checks


def start_background(app, size, fraud_ratio):
    """Used by the API: runs an evaluation in a thread so the request returns
    immediately; the page polls /evaluation/status."""
    if PROGRESS["running"]:
        return False

    def work():
        with app.app_context():
            try:
                run_evaluation(size=size, fraud_ratio=fraud_ratio, mode="IN_PROCESS")
            except Exception:
                app.logger.exception("Background evaluation failed")
            finally:
                db.session.remove()

    _set_progress(running=True, done=0, total=size, error=None)
    threading.Thread(target=work, name="fraudshield-evaluation", daemon=True).start()
    return True
