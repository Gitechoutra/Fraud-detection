"""
portal/services/dataset.py
==========================
The labelled evaluation dataset (specification Table 5.1, phase 4) as a CSV
file: one row per payment an evaluation submitted, with its fraud label, the
story it belongs to, the rules that story is built to fire, and the decision
the engine made.

Labels: 1 = fraud the story is meant to catch, 0 = genuine, empty = build-up
payment of an attack that is not meant to be caught on its own (excluded from
the metrics, see services/simulator.py).

The story set-up rows (logins, new payees, OTP requests) are removed after the
evaluation like everything else, so the file is a record of the evaluated
data set rather than a script to replay; a new data set with the same mix of
stories comes from the same --seed.
"""

import csv
import os

from portal.services import evaluator, simulator

DATASET_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "docs", "evaluation_dataset.csv"))

COLUMNS = [
    "external_ref", "txn_time", "account_id", "amount", "channel", "city", "device_id", "ip_address",
    "merchant_id", "beneficiary_id", "scenario", "expected_rules", "is_fraud_label",
    "decision", "risk_score", "rules_fired", "latency_ms",
]


def _row(r):
    p = r["payload"]
    label = r["label"]
    return {
        "external_ref": p["external_ref"],
        "txn_time": p["txn_time"].isoformat(sep=" ", timespec="seconds") if p.get("txn_time") else "",
        "account_id": p["account_id"],
        "amount": f"{float(p['amount']):.2f}",
        "channel": p["channel"],
        "city": p.get("city") or "",
        "device_id": p.get("device_id") or "",
        "ip_address": p.get("ip_address") or "",
        "merchant_id": p.get("merchant_id") or "",
        "beneficiary_id": p.get("beneficiary_id") or "",
        "scenario": r["scenario"],
        "expected_rules": "+".join(simulator.expected_rules(r["scenario"])),
        "is_fraud_label": "" if label is None else int(label),
        "decision": r["status"],
        "risk_score": r["risk_score"],
        "rules_fired": "+".join(sorted(r["rules"])),
        "latency_ms": f"{r['decision_ms']:.2f}",
    }


def write(rows, path=DATASET_PATH):
    ordered = sorted(rows, key=lambda r: (r["payload"].get("txn_time") is None, r["payload"].get("txn_time")))
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(_row(r) for r in ordered)
    return path


def export(size=5000, fraud_ratio=0.03, workers=8, seed=None, submit=None, mode="IN_PROCESS", path=DATASET_PATH,
           log=print):
    """Runs an evaluation and writes its labelled payments to `path`."""
    m = evaluator.run_evaluation(size=size, fraud_ratio=fraud_ratio, workers=workers, submit=submit, mode=mode,
                                 seed=seed, log=log, with_rows=True)
    write(m["rows"], path)
    log(f"Wrote {len(m['rows'])} labelled payments to {path}")
    return m
