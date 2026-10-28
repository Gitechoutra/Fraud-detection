"""
portal/helpers/auth_helpers.py
==============================
Role checks for staff endpoints, the system API key for ingestion, and the
separate token kind used by the demo bank app.

Roles are ranked: ADMIN > RISK_MANAGER > ANALYST. `min_role("ANALYST")`
means "any staff role"; `min_role("RISK_MANAGER")` means risk managers and
admins. Bank-app tokens (kind="bank") never pass a staff check.
"""

import hmac
from functools import wraps

import bcrypt
from flask import current_app, g, request
from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request

from portal.extensions import db
from portal.helpers.responses import AppError

ROLE_RANK = {"ANALYST": 1, "RISK_MANAGER": 2, "ADMIN": 3}


def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("utf-8")


def check_password(password, password_hash):
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def current_user():
    """The logged-in staff User (cached on g for the request)."""
    from portal.models import User

    identity = get_jwt_identity()
    if g.get("current_user_identity") != identity:
        g.current_user = db.session.get(User, int(identity)) if identity else None
        g.current_user_identity = identity
    return g.current_user


def current_username():
    if has_api_key():
        return "system"
    user = current_user()
    return user.username if user else "system"


def has_api_key():
    supplied = request.headers.get("X-API-Key", "")
    expected = current_app.config.get("INGEST_API_KEY") or ""
    return bool(supplied and expected) and hmac.compare_digest(supplied, expected)


def _check_staff(min_level):
    verify_jwt_in_request()
    claims = get_jwt()
    if claims.get("kind") != "staff":
        raise AppError("This action needs a staff login.", "FORBIDDEN", 403)
    user = current_user()
    if user is None or not user.is_active:
        raise AppError("Your account is disabled.", "FORBIDDEN", 403)
    if ROLE_RANK.get(user.role.name, 0) < ROLE_RANK[min_level]:
        raise AppError("You don't have permission to do this.", "FORBIDDEN", 403)
    return user


def min_role(level):
    """Allows staff whose role ranks at least `level`."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            _check_staff(level)
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def api_key_or_role(level):
    """Allows either a valid X-API-Key header (bank/simulator systems) or a
    staff login of at least `level`."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not has_api_key():
                _check_staff(level)
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def bank_session_required(fn):
    """Demo bank app endpoints: requires a token from /bank-demo/login and
    exposes its claims as g.bank (customer_id, account_id, device_id, ...)."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        claims = get_jwt()
        if claims.get("kind") != "bank":
            raise AppError("Please log in to the bank app first.", "UNAUTHORIZED", 401)
        g.bank = {
            "customer_id": claims["customer_id"],
            "account_id": claims["account_id"],
            "device_id": claims["device_id"],
            "ip_address": claims.get("ip_address"),
            "city": claims.get("city"),
        }
        return fn(*args, **kwargs)

    return wrapper
