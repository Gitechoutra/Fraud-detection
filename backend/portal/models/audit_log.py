from datetime import datetime

from portal.extensions import db
from portal.models.types import DT, iso


class AuditLog(db.Model):
    """Written by DB triggers (rules, watchlist, cases) and by the app for
    user actions such as logins and user management.

    Tamper-evident (portal/sql/03_triggers.sql): a BEFORE INSERT trigger
    chains every row to the previous one with SHA-256 (prev_hash, row_hash),
    and UPDATE / DELETE are refused by triggers. services/audit_chain.py
    re-computes the chain to prove nothing was changed or removed."""

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
    # Filled by the trigger, never by the app.
    prev_hash = db.Column(db.CHAR(64))
    row_hash = db.Column(db.CHAR(64))

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
            "row_hash": self.row_hash,
        }


class AuditChain(db.Model):
    """One row: the hash of the newest audit_log row. The insert trigger
    locks it, so concurrent inserts chain one after another, and it lets the
    verifier notice rows removed from the end of the log."""

    __tablename__ = "audit_chain"

    id = db.Column(db.SmallInteger, primary_key=True, autoincrement=False)
    last_hash = db.Column(db.CHAR(64))
