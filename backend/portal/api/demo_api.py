"""Demo housekeeping: put the five demo customers back to their seeded state
(balances, holds, alerts, watchlist entries their reports created). Staff
or a demo fraudster may call it, and only while DEMO_MODE is on."""

from flask import Blueprint, current_app
from flask_jwt_extended import get_jwt, verify_jwt_in_request

from portal.helpers.auth_helpers import _check_staff, _session_of
from portal.helpers.responses import AppError, ok
from portal.seeders import seed_demo_users

demo_bp = Blueprint("demo", __name__, url_prefix="/demo")


@demo_bp.post("/reset")
def reset():
    if not current_app.config.get("DEMO_MODE"):
        raise AppError("Not found.", "NOT_FOUND", 404)
    verify_jwt_in_request()
    if get_jwt().get("kind") == "fraudster":
        _session_of("fraudster", "FraudsterUser", "Please log in to the simulation console.")
    else:
        _check_staff("ANALYST")
    return ok(seed_demo_users.reset_demo())
