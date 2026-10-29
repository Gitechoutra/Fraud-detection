"""
portal/services/eval_report.py
==============================
The evaluation report (specification 4.13 and Table 5.1, phase 9):
docs/EVALUATION.md, with a pass/fail row for every target in Table 3.1.

run() does a fresh evaluation (also written out as the labelled dataset,
docs/evaluation_dataset.csv), the with/without-index load test, reads the
measured alert freshness, and writes the report. render() only formats, so
it can be tested without running anything.
"""

import os
from datetime import datetime

from portal.helpers.db_helpers import fetch_all
from portal.services import dataset, evaluator, index_benchmark

REPORT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "docs", "EVALUATION.md"))


def _pct(v, places=1):
    return f"{v * 100:.{places}f}%"


def _mark(ok):
    return "✅ Pass" if ok else "❌ Fail"


def _settings():
    rules = fetch_all("SELECT rule_code, simple_name, weight, spec_weight, is_active FROM fraud_rules ORDER BY sort_order")
    bands = {r["setting_key"]: r["setting_value"] for r in fetch_all("SELECT setting_key, setting_value FROM system_settings")}
    return rules, bands


def render(m, bench, fresh, rules, bands, generated_at=None):
    t = m["targets"]
    generated_at = generated_at or datetime.now()
    how = "through the HTTP ingestion API" if m["mode"] == "API" else "in-process (engine called directly)"
    lines = [
        "# Evaluation report",
        "",
        f"*SQL-Based Real-Time Fraud Detection and Transaction Monitoring System* — generated "
        f"{generated_at:%d %b %Y %H:%M} by `flask evaluation-report` (metric run #{m['run_id']}).",
        "",
        "## Data set and method",
        "",
        f"* **{m['submitted']:,}** synthetic payments ({m['total']:,} labelled), {_pct(m['fraud_ratio'])} fraud, "
        f"spread over the last 7 days, sent {how} by parallel workers.",
        "* Normal payments come from customer spending profiles; fraud is injected as labelled stories, one per "
        "rule R1–R9 plus rule combinations (R1+R4, R3+R6, R5+R8).",
        "* The labelled payments are in [`evaluation_dataset.csv`](evaluation_dataset.csv).",
        "* A payment counts as *flagged* when it is held (REVIEW) or blocked. Latency is measured from request "
        "receipt to the **committed** decision.",
        f"* Decision bands: hold from **{bands.get('REVIEW_THRESHOLD', '40')}**, block from "
        f"**{bands.get('BLOCK_THRESHOLD', '70')}**; external model score weight "
        f"{bands.get('MODEL_SCORE_WEIGHT', '0')}% (0 = off).",
        "",
        "## Results against Table 3.1",
        "",
        "| Parameter | Target | Measured | Result |",
        "|---|---|---|---|",
        f"| End-to-end decision latency (p95) | ≤ 500 ms | {m['p95_ms']:.1f} ms (median {m['p50_ms']:.1f} ms) "
        f"| {_mark(t['p95_ms']['pass'])} |",
        f"| Sustained throughput | ≥ 100 TPS | {m['tps']:.0f} TPS | {_mark(t['tps']['pass'])} |",
        f"| Detection rate (recall) | ≥ 90% | {_pct(m['recall'])} ({m['tp']} of {m['tp'] + m['fn']}) "
        f"| {_mark(t['recall']['pass'])} |",
        f"| False-positive rate | ≤ 5% | {_pct(m['fpr'], 2)} ({m['fp']} of {m['fp'] + m['tn']}) "
        f"| {_mark(t['fpr']['pass'])} |",
        f"| Explainability | 100% of flagged list their rules | {_pct(m['explainability'])} "
        f"({m['explained']} of {m['flagged']}) | {_mark(t['explainability']['pass'])} |",
    ]
    if fresh and fresh["measured"]:
        lines.append(
            f"| Dashboard freshness | new alerts visible within 3 s | p95 {fresh['p95_ms'] / 1000:.2f} s, "
            f"max {fresh['max_ms'] / 1000:.2f} s ({fresh['measured']} alerts, commit → first shown on the "
            f"Alerts page) | {_mark(fresh['pass'])} |")
    else:
        lines.append(
            f"| Dashboard freshness | new alerts visible within 3 s | worst case {m['alert_visible_ms'] / 1000:.2f} s "
            f"(p95 decision + queue read + 2 s refresh; not yet measured on screen) "
            f"| {_mark(t['alert_visible_ms']['pass'])} |")
    lines += [
        "",
        f"Precision **{_pct(m['precision'])}**, F1-score **{_pct(m['f1'])}**.",
        "",
        "## Confusion matrix",
        "",
        "| | Flagged | Approved |",
        "|---|---|---|",
        f"| **Fraud** | {m['tp']} (TP) | {m['fn']} (FN) |",
        f"| **Genuine** | {m['fp']} (FP) | {m['tn']} (TN) |",
        "",
        "## Per fraud story",
        "",
        "| Story | Rules it must fire | All fired | Caught (recall) |",
        "|---|---|---|---|",
    ]
    for s in m["per_scenario"]:
        recall = "—" if s["recall"] is None else _pct(s["recall"], 0)
        lines.append(f"| {s['scenario']} | {' + '.join(s['rules'])} | {s['rule_fired']}/{s['count']} "
                     f"| {s['caught']}/{s['count']} ({recall}) |")
    lines += [
        "",
        "## Per rule",
        "",
        "| Rule | Name | Weight (tuned) | Weight (spec) | Fired | Precision |",
        "|---|---|---|---|---|---|",
    ]
    per_rule = {r["rule_code"]: r for r in m["per_rule"]}
    for r in rules:
        pr = per_rule.get(r["rule_code"], {})
        prec = "—" if pr.get("precision") is None else _pct(pr["precision"], 0)
        state = "" if r["is_active"] else " (off)"
        lines.append(f"| {r['rule_code']} | {r['simple_name']}{state} | {r['weight']} | {r['spec_weight'] or '—'} "
                     f"| {pr.get('hits', 0)} | {prec} |")
    lines += ["", "## Load test with and without the composite indexes", ""]
    if bench:
        i, n = bench["indexed"], bench["no_index"]
        lines += [
            "Same labelled payments, first with the composite `(account_id, txn_time)` and "
            "`(account_id, city, txn_time)` indexes, then with only a plain `(account_id)` index.",
            "",
            "| | With indexes | Without | |",
            "|---|---|---|---|",
            f"| Latency p50 | {i['p50_ms']:.1f} ms | {n['p50_ms']:.1f} ms | |",
            f"| Latency p95 | {i['p95_ms']:.1f} ms | {n['p95_ms']:.1f} ms | {bench['p95_speedup']}× faster with indexes |",
            f"| Throughput | {i['tps']:.0f} TPS | {n['tps']:.0f} TPS | {bench['tps_gain']}× with indexes |",
            f"| Recall | {_pct(i['recall'])} | {_pct(n['recall'])} | same rules, same result |",
        ]
    else:
        lines.append("Not run this time (`flask evaluation-report --skip-benchmark`).")
    lines += [
        "",
        "## Notes",
        "",
        "* Rule weights were tuned from the specification's starting values (Table 4.4); see "
        "[RULES.md](RULES.md#how-the-weights-were-tuned) for why. Thresholds are the specification's.",
        "* Every number here comes from one run on synthetic data on a single machine; rerun "
        "`flask evaluation-report` to reproduce it.",
        "",
    ]
    return "\n".join(lines)


def run(size=5000, bench_size=2000, fraud_ratio=0.03, workers=8, submit=None, mode="IN_PROCESS", seed=None,
        benchmark=True, path=REPORT_PATH, dataset_path=dataset.DATASET_PATH, log=print):
    log("1/3 Evaluation")
    m = dataset.export(size=size, fraud_ratio=fraud_ratio, workers=workers, seed=seed, submit=submit, mode=mode,
                       path=dataset_path, log=log)
    bench = None
    if benchmark:
        log("2/3 Load test with and without the composite indexes")
        bench = index_benchmark.run(size=bench_size, fraud_ratio=fraud_ratio, workers=workers, seed=seed,
                                    submit=submit, log=log)
    log("3/3 Measured alert freshness and settings")
    rules, bands = _settings()
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render(m, bench, evaluator.measured_alert_freshness(30), rules, bands))
    log(f"Wrote {path}")
    return {"metrics": m, "benchmark": bench, "path": path}
