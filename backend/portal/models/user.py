from datetime import datetime

from portal.extensions import db
from portal.models.types import DT, iso


class Role(db.Model):
    __tablename__ = "roles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), unique=True, nullable=False)
    description = db.Column(db.String(255))


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(DT, nullable=False, default=datetime.now)
    last_login_at = db.Column(DT)

    role = db.relationship("Role", lazy="joined")

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "full_name": self.full_name,
            "role": self.role.name if self.role else None,
            "is_active": self.is_active,
            "created_at": iso(self.created_at),
            "last_login_at": iso(self.last_login_at),
        }


class TokenBlocklist(db.Model):
    """Revoked JWTs (logout). Checked on every authenticated request."""

    __tablename__ = "token_blocklist"

    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(64), unique=True, nullable=False)
    token_type = db.Column(db.String(16), nullable=False)
    revoked_at = db.Column(DT, nullable=False, default=datetime.now)
