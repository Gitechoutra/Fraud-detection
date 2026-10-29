"""Start an evaluation run (in the background) and read past results."""

from flask import Blueprint, current_app, request

from portal.helpers.auth_helpers import min_role
from portal.helpers.responses import AppError, ok
from portal.helpers.validators import EvaluationRunSchema, load
from portal.models import MetricRun
from portal.services import evaluator, index_benchmark

evaluation_bp = Blueprint("evaluation", __name__, url_prefix="/evaluation")


def _evaluations():
    """Regular evaluation runs (index-benchmark runs are shown separately)."""
    return MetricRun.query.filter(~MetricRun.mode.like("BENCH%"))


def _with_targets(run):
    data = run.to_dict()
    data["targets"] = evaluator.target_checks(data)
    return data


@evaluation_bp.post("/run")
@min_role("RISK_MANAGER")
def run():
    data = load(EvaluationRunSchema, request.get_json(silent=True))
    started = evaluator.start_background(current_app._get_current_object(), data["size"], data["fraud_ratio"])
    if not started:
        raise AppError("An evaluation is already running.", "ALREADY_RUNNING", 409)
    return ok({"started": True, "progress": dict(evaluator.PROGRESS)}, 202)


@evaluation_bp.get("/status")
@min_role("RISK_MANAGER")
def status():
    return ok(dict(evaluator.PROGRESS))


@evaluation_bp.get("/latest")
@min_role("RISK_MANAGER")
def latest():
    run_ = _evaluations().order_by(MetricRun.id.desc()).first()
    return ok(_with_targets(run_) if run_ else None)


@evaluation_bp.get("/history")
@min_role("RISK_MANAGER")
def history():
    runs = _evaluations().order_by(MetricRun.id.desc()).limit(30).all()
    return ok({"runs": [_with_targets(r) for r in reversed(runs)], "targets": evaluator.TARGETS})


@evaluation_bp.get("/index-benchmark")
@min_role("RISK_MANAGER")
def latest_index_benchmark():
    """The newest with/without-index pair (`flask benchmark-indexes`)."""
    unindexed = MetricRun.query.filter_by(mode="BENCH_NO_INDEX").order_by(MetricRun.id.desc()).first()
    indexed = unindexed and MetricRun.query.filter(
        MetricRun.mode == "BENCH_INDEXED", MetricRun.id < unindexed.id).order_by(MetricRun.id.desc()).first()
    if not indexed:
        return ok(None)
    return ok(index_benchmark.compare(_bench_row(indexed), _bench_row(unindexed)))


def _bench_row(run_):
    d = run_.to_dict()
    return {k: d[k] for k in ("run_at", "total", "p50_ms", "p95_ms", "tps", "recall", "fpr")} | {"run_id": run_.id}
