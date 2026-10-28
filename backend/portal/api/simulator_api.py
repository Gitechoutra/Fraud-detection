"""Fraud Lab: run one fraud story, or start/stop a live traffic stream."""

from flask import Blueprint, current_app, request

from portal.helpers.auth_helpers import min_role
from portal.helpers.responses import AppError, ok
from portal.helpers.validators import StreamStartSchema, load
from portal.services import simulator

simulator_bp = Blueprint("simulator", __name__, url_prefix="/simulator")


@simulator_bp.get("/scenarios")
@min_role("ANALYST")
def scenarios():
    return ok([{"code": code, "story": story} for code, story in simulator.STORIES.items()])


@simulator_bp.post("/scenario/<code>")
@min_role("RISK_MANAGER")
def run_scenario(code):
    if code.upper() not in simulator.SCENARIOS:
        raise AppError("Unknown scenario. Use NORMAL or R1..R9.", "NOT_FOUND", 404)
    try:
        return ok(simulator.run_scenario(code))
    except RuntimeError as exc:
        raise AppError(str(exc), "NOT_SEEDED", 409)


@simulator_bp.post("/stream/start")
@min_role("RISK_MANAGER")
def stream_start():
    data = load(StreamStartSchema, request.get_json(silent=True))
    app = current_app._get_current_object()
    return ok(simulator.STREAM.start(app, rate=data["rate"], fraud_ratio=data["fraud_ratio"]))


@simulator_bp.post("/stream/stop")
@min_role("RISK_MANAGER")
def stream_stop():
    return ok(simulator.STREAM.stop())


@simulator_bp.get("/stream/status")
@min_role("ANALYST")
def stream_status():
    return ok(simulator.STREAM.status())
