from datetime import datetime

from portal.extensions import db
from portal.models.types import DT, iso


class AuditLog(db.Model):
    """Written by DB triggers (rules, watchlist, cases) and by the app for
    user actions such as logins and user management."""

    __tablename__ = "audit_log"
    __table_args__ = (db.Index("ix_audit_logged_at", "logged_at"),)

    id = db.Column(db.BigInteger, primary_key=True)
    actor = db.Column(db.String(64), nullable=False)
    action = db.Column(db.String(32), nullable=False)
    entity = db.Column(db.String(32), nullable=False)
    entity_id = db.Column(db.String(64))
    old_value = db.Column(db.JSON)
    new_value = db.Column(db.JSON)
    logged_at = db.Column(DT, nullable=False, default=datetime.now)

    def to_dict(self):
        return {
            "id": self.id,
            "actor": self.actor,
            "action": self.action,
            "entity": self.entity,
            "entity_id": self.entity_id,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "logged_at": iso(self.logged_at),
        }
