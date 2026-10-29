"""
portal/services/index_benchmark.py
==================================
Load test with and without the composite indexes (specification 4.11,
phase 8).

Runs the same labelled evaluation twice -- same size, same random seed, so
the same mix of stories -- first with the indexes, then with them dropped,
and reports latency and throughput side by side. Both runs are saved in
metric_runs (mode BENCH_INDEXED / BENCH_NO_INDEX) and their test payments are
deleted as usual.

MySQL needs *some* index starting with account_id for the foreign key, so
while the composite ones are gone a plain (account_id) index stands in; the
comparison is therefore "composite (account_id, txn_time) index" versus
"account_id only", which is exactly what the composite index adds. The
indexes are always put back, even if a run fails.
"""

import random

from sqlalchemy import text

from portal.extensions import db
from portal.services import evaluator

# (name, columns) of the composite indexes on transactions (01_indexes.sql).
COMPOSITE_INDEXES = [
    ("ix_txn_account_time", "account_id, txn_time"),
    ("ix_txn_account_city_time", "account_id, city, txn_time"),
]
STAND_IN = "ix_bench_txn_account"


def _existing():
    return {r[0] for r in db.session.execute(
        text("SELECT DISTINCT index_name FROM information_schema.statistics "
             "WHERE table_schema = DATABASE() AND table_name = 'transactions'"))}


def _drop_composites(log):
    if STAND_IN not in _existing():
        db.session.execute(text(f"CREATE INDEX {STAND_IN} ON transactions (account_id)"))
    for name, _ in COMPOSITE_INDEXES:
        if name in _existing():
            db.session.execute(text(f"DROP INDEX {name} ON transactions"))
    log("  composite indexes dropped")


def _restore(log):
    present = _existing()
    for name, cols in COMPOSITE_INDEXES:
        if name not in present:
            db.session.execute(text(f"CREATE INDEX {name} ON transactions ({cols})"))
    if STAND_IN in _existing():
        db.session.execute(text(f"DROP INDEX {STAND_IN} ON transactions"))
    log("  composite indexes restored")


def _row(m):
    return {"run_id": m["run_id"], "p50_ms": m["p50_ms"], "p95_ms": m["p95_ms"], "tps": m["tps"],
            "recall": m["recall"], "fpr": m["fpr"]}


def compare(indexed, unindexed):
    """Side-by-side numbers, and how much the indexes help."""
    return {
        "indexed": indexed,
        "no_index": unindexed,
        "p95_speedup": round(unindexed["p95_ms"] / indexed["p95_ms"], 2) if indexed["p95_ms"] else None,
        "tps_gain": round(indexed["tps"] / unindexed["tps"], 2) if unindexed["tps"] else None,
    }


def run(size=2000, fraud_ratio=0.03, workers=8, seed=None, submit=None, log=print):
    """`submit` (evaluator.http_submitter) sends the load through the
    ingestion API, as the specification's load test does; without it the
    engine is called in-process."""
    seed = seed if seed is not None else random.randint(0, 10**9)
    log(f"Index benchmark: {size} payments, seed {seed}, {'over the API' if submit else 'in-process'}")
    log("Run 1/2 with the composite indexes")
    indexed = evaluator.run_evaluation(size=size, fraud_ratio=fraud_ratio, workers=workers, submit=submit,
                                       mode="BENCH_INDEXED", seed=seed, log=log)
    try:
        _drop_composites(log)
        log("Run 2/2 without them")
        unindexed = evaluator.run_evaluation(size=size, fraud_ratio=fraud_ratio, workers=workers, submit=submit,
                                             mode="BENCH_NO_INDEX", seed=seed, log=log)
    finally:
        db.session.rollback()
        _restore(log)
    result = compare(_row(indexed), _row(unindexed))
    log(f"p95 {result['indexed']['p95_ms']} ms vs {result['no_index']['p95_ms']} ms "
        f"({result['p95_speedup']}x faster with indexes); "
        f"{result['indexed']['tps']} vs {result['no_index']['tps']} TPS")
    return result
