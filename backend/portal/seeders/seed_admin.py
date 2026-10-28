"""Default staff users, credentials from .env."""

import os

from portal.extensions import db
from portal.helpers.auth_helpers import check_password, hash_password
from portal.models import Role, User


def default_users():
    return [
        (os.environ.get("ADMIN_USERNAME", "admin"), os.environ.get("ADMIN_PASSWORD", "Admin@123"),
         "Asha Admin", "ADMIN"),
        (os.environ.get("RISK_USERNAME", "risk"), os.environ.get("RISK_PASSWORD", "Risk@123"),
         "Rahul Risk Manager", "RISK_MANAGER"),
        (os.environ.get("ANALYST_USERNAME", "analyst"), os.environ.get("ANALYST_PASSWORD", "Analyst@123"),
         "Anita Analyst", "ANALYST"),
    ]


def run(log=print):
    """Creates the default users, and keeps them in step with .env: a changed
    password is re-hashed, and a changed username renames the original user of
    that role (the oldest one), so its history stays attached."""
    roles = {r.name: r.id for r in Role.query.all()}
    added = updated = 0
    for username, password, full_name, role in default_users():
        user = User.query.filter_by(username=username).first()
        if user is None:
            user = User.query.filter_by(role_id=roles[role]).order_by(User.id).first()
            if user is not None:
                user.username = username
                updated += 1
        if user is None:
            db.session.add(
                User(username=username, full_name=full_name, password_hash=hash_password(password),
                     role_id=roles[role], is_active=True)
            )
            added += 1
            continue
        if not check_password(password, user.password_hash):
            user.password_hash = hash_password(password)
            updated += 1
    db.session.commit()
    log(f"  users: {added} added, {updated} updated from .env")
