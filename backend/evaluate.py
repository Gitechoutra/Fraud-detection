"""
evaluate.py -- measure FraudShield on a fresh labelled data set.

    python evaluate.py                         # 5,000 payments, 3% fraud, through the running API
    python evaluate.py --size 2000 --in-process
    python evaluate.py --keep                  # keep the evaluation rows for inspection

Payments are sent to POST /api/transactions (with the X-API-Key from .env)
when the API is reachable; otherwise the engine is called in-process. Story
set-up steps (logins, new payees, OTP requests) are written directly.
Prints the metrics, saves a metric_runs row and writes evaluation_results.json.
"""

import argparse
import json
import sys

from portal import create_app
from portal.services.evaluator import TARGETS, api_reachable, http_submitter, run_evaluation

def main():
    parser = argparse.ArgumentParser(description="Evaluate FraudShield's rules on labelled synthetic data.")
    parser.add_argument("--size", type=int, default=5000, help="labelled payments to generate (default 5000)")
    parser.add_argument("--fraud-ratio", type=float, default=0.03, help="share of fraud (default 0.03)")
    parser.add_argument("--days", type=int, default=7, help="spread payments over the last N days (default 7)")
    parser.add_argument("--workers", type=int, default=12, help="parallel workers (default 12)")
    parser.add_argument("--api-url", default="http://127.0.0.1:5000/api")
    parser.add_argument("--in-process", action="store_true", help="call the engine directly instead of the API")
    parser.add_argument("--keep", action="store_true", help="keep the generated rows")
    parser.add_argument("--seed", type=int, default=None, help="random seed for a repeatable run")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        submit, mode = None, "IN_PROCESS"
        if not args.in_process:
            if api_reachable(args.api_url):
                submit, mode = http_submitter(args.api_url, app.config["INGEST_API_KEY"]), "API"
            else:
                print(f"API at {args.api_url} is not reachable -- evaluating in-process instead.")
        m = run_evaluation(size=args.size, fraud_ratio=args.fraud_ratio, days=args.days, workers=args.workers,
                           submit=submit, mode=mode, keep=args.keep, seed=args.seed, log=print)

    print()
    print(f"{'Metric':<22}{'Value':>12}   Target")
    print("-" * 48)
    rows = [
        ("Recall (fraud caught)", f"{m['recall']:.2%}", f">= {TARGETS['recall']:.0%}", m["targets"]["recall"]["pass"]),
        ("False-positive rate", f"{m['fpr']:.2%}", f"<= {TARGETS['fpr']:.0%}", m["targets"]["fpr"]["pass"]),
        ("Precision", f"{m['precision']:.2%}", "", None),
        ("F1 score", f"{m['f1']:.2%}", "", None),
        ("Latency p50", f"{m['p50_ms']:.1f} ms", "", None),
        ("Latency p95", f"{m['p95_ms']:.1f} ms", f"<= {TARGETS['p95_ms']:.0f} ms", m["targets"]["p95_ms"]["pass"]),
        ("Throughput", f"{m['tps']:.0f} TPS", f">= {TARGETS['tps']:.0f} TPS", m["targets"]["tps"]["pass"]),
        ("Explainability", f"{m['explainability']:.1%}", "100%", m["targets"]["explainability"]["pass"]),
        ("Alert on screen", f"{m['alert_visible_ms']:.0f} ms", f"<= {TARGETS['alert_visible_ms']:.0f} ms",
         m["targets"]["alert_visible_ms"]["pass"]),
    ]
    for name, value, target, ok in rows:
        mark = "" if ok is None else ("  PASS" if ok else "  FAIL")
        print(f"{name:<22}{value:>12}   {target}{mark}")
    print(f"\nConfusion matrix: TP={m['tp']}  FP={m['fp']}  TN={m['tn']}  FN={m['fn']}  "
          f"(labelled {m['total']}, submitted {m['submitted']}, mode {mode})")
    print("\nPer fraud story:")
    for s in m["per_scenario"]:
        print(f"  {s['scenario']}: caught {s['caught']}/{s['count']}  (its rule fired {s['rule_fired']}/{s['count']})")
    with open("evaluation_results.json", "w", encoding="utf-8") as fh:
        json.dump(m, fh, indent=2, default=str)
    print("\nSaved to evaluation_results.json and metric_runs #%s" % m["run_id"])
    return 0 if all(t["pass"] for t in m["targets"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
