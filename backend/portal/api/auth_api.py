"""Staff login with JWT access (15 min) + refresh (7 days) tokens."""

from datetime import datetime

from flask import Blueprint, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
)

from portal.extensions import db, limiter
from portal.helpers.auth_helpers import check_password, current_user
from portal.helpers.responses import AppError, ok
from portal.helpers.validators import LoginSchema, LogoutSchema, load
from portal.models import AuditLog, TokenBlocklist, User

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _tokens(user):
    claims = {"kind": "staff", "role": user.role.name, "username": user.username}
    return {
        "access_token": create_access_token(identity=str(user.id), additional_claims=claims),
        "refresh_token": create_refresh_token(identity=str(user.id), additional_claims=claims),
    }


def _revoke(jti, token_type):
    if not TokenBlocklist.query.filter_by(jti=jti).first():
        db.session.add(TokenBlocklist(jti=jti, token_type=token_type))


@auth_bp.post("/login")
@limiter.limit("10 per minute")
def login():
    data = load(LoginSchema, request.get_json(silent=True))
    user = User.query.filter_by(username=data["username"].strip()).first()
    if user is None or not check_password(data["password"], user.password_hash):
        raise AppError("Wrong username or password.", "INVALID_CREDENTIALS", 401)
    if not user.is_active:
        raise AppError("This account is disabled. Ask an admin.", "ACCOUNT_DISABLED", 403)
    user.last_login_at = datetime.now()
    db.session.add(AuditLog(actor=user.username, action="LOGIN", entity="users", entity_id=str(user.id)))
    db.session.commit()
    return ok({**_tokens(user), "user": user.to_dict()})


@auth_bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    if get_jwt().get("kind") != "staff":
        raise AppError("Please log in again.", "UNAUTHORIZED", 401)
    user = db.session.get(User, int(get_jwt_identity()))
    if user is None or not user.is_active:
        raise AppError("Please log in again.", "UNAUTHORIZED", 401)
    claims = {"kind": "staff", "role": user.role.name, "username": user.username}
    return ok({"access_token": create_access_token(identity=str(user.id), additional_claims=claims)})


@auth_bp.get("/me")
@jwt_required()
def me():
    if get_jwt().get("kind") != "staff":
        raise AppError("Please log in again.", "UNAUTHORIZED", 401)
    user = current_user()
    if user is None:
        raise AppError("Please log in again.", "UNAUTHORIZED", 401)
    return ok(user.to_dict())


@auth_bp.post("/logout")
@jwt_required(verify_type=False)
def logout():
    """Revokes the token used for this call, plus the refresh token if sent."""
    payload = get_jwt()
    _revoke(payload["jti"], payload["type"])
    data = load(LogoutSchema, request.get_json(silent=True))
    if data.get("refresh_token"):
        try:
            refresh_payload = decode_token(data["refresh_token"], allow_expired=True)
            if refresh_payload.get("sub") == payload.get("sub"):
                _revoke(refresh_payload["jti"], "refresh")
        except Exception:
            pass  # an unreadable refresh token can't be used anyway
    db.session.commit()
    return ok({"logged_out": True})
