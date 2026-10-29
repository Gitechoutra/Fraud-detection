from datetime import datetime

from portal.extensions import db
from portal.models.types import DT


class Alert(db.Model):
    """Raised for every REVIEW/BLOCKED transaction (by the stored procedure)
    and when a customer answers NO to an OTP Shield approval."""

    __tablename__ = "alerts"
    __table_args__ = (db.Index("ix_alerts_status_created", "alert_status", "created_at"),)

    id = db.Column(db.BigInteger, primary_key=True)
    txn_id = db.Column(db.BigInteger, db.ForeignKey("transactions.id", ondelete="CASCADE"), unique=True)
    otp_request_id = db.Column(db.BigInteger, db.ForeignKey("otp_requests.id", ondelete="CASCADE"))
    source = db.Column(db.String(16), nullable=False, default="TRANSACTION")  # TRANSACTION / OTP_SHIELD
    summary = db.Column(db.String(255))
    risk_score = db.Column(db.SmallInteger, nullable=False)
    priority = db.Column(db.Enum("MEDIUM", "HIGH", name="alert_priority"), nullable=False)
    alert_status = db.Column(
        db.Enum("OPEN", "IN_PROGRESS", "CLOSED", name="alert_status"), nullable=False, default="OPEN"
    )
    assigned_to = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(DT, nullable=False, default=datetime.now)
    updated_at = db.Column(DT, nullable=False, default=datetime.now, onupdate=datetime.now)
    # When the alert queue first showed it on an analyst's screen (reported by
    # the Alerts page); first_seen_at - created_at is the measured freshness.
    first_seen_at = db.Column(DT)
