"""
Fraudster simulation console (/attacker) -- SIMULATION ONLY, local demo.

Disabled unless DEMO_MODE is on (it is off in the production config). A
fraudster token (kind "fraudster") can see only the credentials linked to
that fraudster and run the fixed attack patterns in services/attacker; every
attack payment goes through fraud_engine.ingest.
"""

from functools import wraps

from flask import Blueprint, current_app, g
from flask_jwt_extended import get_jwt

from portal.api.auth_api import _revoke
from portal.extensions import db, limiter
from portal.helpers.auth_helpers import check_password, fraudster_required
from portal.helpers.db_helpers import jsonable
from portal.helpers.demo_context import demo_city, device_id, issue_token, network_address
from portal.helpers.responses import AppError, ok
from portal.helpers.validators import DemoLoginSchema, load
from portal.models import FraudsterUser
from portal.services import attacker

attacker_bp = Blueprint("attacker", __name__, url_prefix="/attacker")


def demo_only(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_app.config.get("DEMO_MODE"):
            raise AppError("Not found.", "NOT_FOUND", 404)
        return fn(*args, **kwargs)

    return wrapper


def _me(user):
    return {
        "username": user.username,
        "display_name": user.display_name,
        "base_city": user.base_city,
        "city": demo_city(user.base_city),
        "device_id": device_id(),
        "credentials": attacker.credentials(user.id),
        "scenarios": [{"code": k, "title": v["title"], "story": v["story"], "rules": v["rules"]}
                      for k, v in attacker.SCENARIOS.items()],
    }


@attacker_bp.post("/login")
@demo_only
@limiter.limit("10 per minute")
def login():
    from flask import request

    data = load(DemoLoginSchema, request.get_json(silent=True))
    user = FraudsterUser.query.filter_by(username=data["username"]).first()
    if user is None or not check_password(data["password"], user.password_hash):
        raise AppError("Wrong username or password.", "INVALID_CREDENTIALS", 401)
    return ok({"token": issue_token("fraudster", user.id), **_me(user)})


@attacker_bp.post("/logout")
@demo_only
@fraudster_required
def logout():
    _revoke(get_jwt()["jti"], "access")
    db.session.commit()
    return ok({"logged_out": True})


@attacker_bp.get("/me")
@demo_only
@fraudster_required
def me():
    return ok(_me(g.fraudster))


@attacker_bp.post("/attack/<code>")
@demo_only
@limiter.limit("30 per minute")
@fraudster_required
def attack(code):
    device = device_id()
    result = attacker.run(g.fraudster, code, device, network_address(device, fraudster=True),
                          demo_city(g.fraudster.base_city))
    return ok(result, 201)


@attacker_bp.get("/events")
@demo_only
@fraudster_required
def events():
    return ok([jsonable(r) for r in attacker.recent(g.fraudster.id)])
