from datetime import datetime

from portal.extensions import db
from portal.models.types import DT, iso

SESSION_EVENTS = (
    "LOGIN",
    "OTP_REQUEST",
    "OTP_VERIFY",
    "PASSWORD_RESET",
    "SIM_CHANGE",
    "MOBILE_CHANGE",
)


class SessionEvent(db.Model):
    """A security event on an account (login, SIM change, ...). Named
    SessionEvent so it never gets confused with db.session."""

    __tablename__ = "sessions"
    __table_args__ = (
        db.Index("ix_sessions_account_event_time", "account_id", "event_type", "created_at"),
    )

    id = db.Column(db.BigInteger, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    device_id = db.Column(db.String(64))
    ip_address = db.Column(db.String(45))
    city = db.Column(db.String(64))
    event_type = db.Column(db.Enum(*SESSION_EVENTS, name="session_event"), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(DT, nullable=False, default=datetime.now)

    def to_dict(self):
        return {
            "id": self.id,
            "account_id": self.account_id,
            "device_id": self.device_id,
            "ip_address": self.ip_address,
            "city": self.city,
            "event_type": self.event_type,
            "is_active": self.is_active,
            "created_at": iso(self.created_at),
        }
