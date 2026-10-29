"""
simulate.py -- stream synthetic payments to the running FraudShield API.

    python simulate.py --rate 5 --fraud-ratio 0.03 --minutes 2

Each payment is POSTed to /api/transactions with the X-API-Key from .env, so
it appears on the Live Monitor exactly like a real bank's traffic. Fraud
stories (R1-R9) are mixed in at --fraud-ratio. A demo customer pays at most
once every 150 seconds, so the achievable normal rate is capped by the number
of demo accounts (about 2 per second with the default 200 customers).
"""

import argparse
import random
import sys
import time
from datetime import datetime

from portal import create_app
from portal.extensions import db
from portal.services import simulator
from portal.services.evaluator import api_reachable, http_submitter

ACCOUNT_SPACING = 150


def main():
    parser = argparse.ArgumentParser(description="Stream synthetic payments to the FraudShield API.")
    parser.add_argument("--rate", type=float, default=5.0, help="payments per second (default 5)")
    parser.add_argument("--fraud-ratio", type=float, default=0.03, help="share of fraud stories (default 0.03)")
    parser.add_argument("--minutes", type=float, default=2.0, help="how long to run (default 2)")
    parser.add_argument("--api-url", default="http://127.0.0.1:5000/api")
    args = parser.parse_args()

    app = create_app()
    if not api_reachable(args.api_url):
        print(f"The API at {args.api_url} is not reachable. Start the backend first (start_backend.bat).")
        return 1
    rng = random.Random()
    last_used = {}
    counts = {"APPROVED": 0, "REVIEW": 0, "BLOCKED": 0, "fraud": 0, "errors": 0}
    end = time.time() + args.minutes * 60
    with app.app_context():
        submit = http_submitter(args.api_url, app.config["INGEST_API_KEY"])
        profiles = simulator.get_cache(force=True)["profiles"]
        print(f"Streaming for {args.minutes} min at up to {args.rate}/s ({args.fraud_ratio:.0%} fraud) "
              f"over {len(profiles)} demo accounts. Ctrl+C to stop.")
        try:
            while time.time() < end:
                tick = time.time()
                ctx = simulator.ScenarioContext(source="SIMULATOR", live=True, rng=rng, submit=submit, prefix="CLI")
                try:
                    if rng.random() < args.fraud_ratio:
                        codes = [c for c in simulator.RULE_CODES if c != "R5" or datetime.now().hour < 5]
                        code = rng.choice(codes)
                        result = simulator.SCENARIOS[code](ctx)
                        counts["fraud"] += 1
                    else:
                        free = [p for p in profiles if tick - last_used.get(p["account_id"], 0) > ACCOUNT_SPACING]
                        if not free:
                            time.sleep(0.5)
                            continue
                        profile = rng.choice(free)
                        last_used[profile["account_id"]] = tick
                        code = "NORMAL"
                        result = simulator.normal_payment(ctx, profile)
                    counts[result["status"]] += 1
                    rules = ",".join(h["rule_code"] for h in result["rules"]) or "-"
                    print(f"{datetime.now():%H:%M:%S} {code:<6} ₹{result['amount']:>11,.2f}  "
                          f"{result['status']:<8} score {result['risk_score']:>3}  rules {rules:<12} "
                          f"{result['decision_ms']:.1f} ms")
                except Exception as exc:
                    db.session.rollback()
                    counts["errors"] += 1
                    print(f"  error: {exc}")
                finally:
                    db.session.remove()
                time.sleep(max(0.0, 1.0 / args.rate - (time.time() - tick)))
        except KeyboardInterrupt:
            pass
    total = counts["APPROVED"] + counts["REVIEW"] + counts["BLOCKED"]
    print(f"\nSent {total}: approved {counts['APPROVED']}, held {counts['REVIEW']}, blocked {counts['BLOCKED']} "
          f"({counts['fraud']} fraud stories, {counts['errors']} errors)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
