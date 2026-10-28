"""Admin: manage staff users and their roles."""

from flask import Blueprint, request

from portal.extensions import db
from portal.helpers.auth_helpers import current_user, hash_password, min_role
from portal.helpers.responses import AppError, ok
from portal.helpers.validators import UserCreateSchema, UserUpdateSchema, load
from portal.models import AuditLog, Role, User

users_bp = Blueprint("users", __name__, url_prefix="/users")


def _role_id(name):
    role = Role.query.filter_by(name=name).first()
    if role is None:
        raise AppError("Unknown role.", "BAD_ROLE", 400)
    return role.id


@users_bp.get("")
@min_role("ADMIN")
def list_users():
    return ok([u.to_dict() for u in User.query.order_by(User.id).all()])


@users_bp.post("")
@min_role("ADMIN")
def create_user():
    data = load(UserCreateSchema, request.get_json(silent=True))
    if User.query.filter_by(username=data["username"]).first():
        raise AppError("That username is taken.", "DUPLICATE", 409)
    user = User(username=data["username"], full_name=data["full_name"].strip(),
                password_hash=hash_password(data["password"]), role_id=_role_id(data["role"]), is_active=True)
    db.session.add(user)
    db.session.flush()
    db.session.add(AuditLog(actor=current_user().username, action="USER_CREATED", entity="users",
                            entity_id=str(user.id), new_value={"username": user.username, "role": data["role"]}))
    db.session.commit()
    return ok(user.to_dict(), 201)


@users_bp.patch("/<int:user_id>")
@min_role("ADMIN")
def update_user(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        raise AppError("We couldn't find that user.", "NOT_FOUND", 404)
    data = load(UserUpdateSchema, request.get_json(silent=True))
    me = current_user()
    if user.id == me.id and (data["is_active"] is False or (data["role"] and data["role"] != "ADMIN")):
        raise AppError("You can't disable yourself or remove your own admin role.", "SELF_LOCKOUT", 400)
    old = user.to_dict()
    if data["full_name"]:
        user.full_name = data["full_name"].strip()
    if data["password"]:
        user.password_hash = hash_password(data["password"])
    if data["role"]:
        user.role_id = _role_id(data["role"])
    if data["is_active"] is not None:
        user.is_active = data["is_active"]
    db.session.flush()
    db.session.refresh(user)
    db.session.add(AuditLog(actor=me.username, action="USER_UPDATED", entity="users", entity_id=str(user.id),
                            old_value={"role": old["role"], "is_active": old["is_active"]},
                            new_value={"role": user.role.name, "is_active": user.is_active,
                                       "password_changed": bool(data["password"])}))
    db.session.commit()
    return ok(user.to_dict())
