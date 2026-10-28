"""Default staff users, credentials from .env."""

import os

from portal.extensions import db
from portal.helpers.auth_helpers import hash_password
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
    roles = {r.name: r.id for r in Role.query.all()}
    added = 0
    for username, password, full_name, role in default_users():
        if User.query.filter_by(username=username).first() is None:
            db.session.add(
                User(username=username, full_name=full_name, password_hash=hash_password(password),
                     role_id=roles[role], is_active=True)
            )
            added += 1
    db.session.commit()
    log(f"  users: {added} added")
