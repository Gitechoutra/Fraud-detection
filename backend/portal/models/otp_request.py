from datetime import datetime

from portal.extensions import db
from portal.models.types import DT, MONEY, iso

OTP_DECISIONS = ("OTP_SENT", "OTP_SENT_WITH_WARNING", "OTP_BLOCKED_APPROVAL_REQUIRED")
OTP_STATES = ("PENDING", "VERIFIED", "EXPIRED", "LOCKED", "APPROVED", "DENIED")


class OtpRequest(db.Model):
    """Every OTP Shield check (R9-A), whether or not an OTP was sent. Also
    holds the payment it is for, so the payment can run once verified."""

    __tablename__ = "otp_requests"
    __table_args__ = (db.Index("ix_otp_account_created", "account_id", "created_at"),)

    id = db.Column(db.BigInteger, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    beneficiary_id = db.Column(db.Integer, db.ForeignKey("beneficiaries.id"))
    amount = db.Column(MONEY, nullable=False)
    requesting_device_id = db.Column(db.String(64))
    ip_address = db.Column(db.String(45))
    city = db.Column(db.String(64))
    risk_points = db.Column(db.SmallInteger, nullable=False, default=0)
    signals_json = db.Column(db.JSON)
    decision = db.Column(db.Enum(*OTP_DECISIONS, name="otp_decision"), nullable=False)
    final_status = db.Column(db.Enum(*OTP_STATES, name="otp_state"), nullable=False, default="PENDING")
    otp_hash = db.Column(db.String(64))
    attempts = db.Column(db.SmallInteger, nullable=False, default=0)
    expires_at = db.Column(DT)
    verified_at = db.Column(DT)
    verified_device_id = db.Column(db.String(64))
    verified_ip = db.Column(db.String(45))  # where the OTP was typed (rule R9 checks it)
    txn_id = db.Column(db.BigInteger)
    created_at = db.Column(DT, nullable=False, default=datetime.now)

    def to_dict(self):
        return {
            "id": self.id,
            "account_id": self.account_id,
            "beneficiary_id": self.beneficiary_id,
            "amount": float(self.amount),
            "requesting_device_id": self.requesting_device_id,
            "ip_address": self.ip_address,
            "city": self.city,
            "risk_points": self.risk_points,
            "signals": self.signals_json or [],
            "decision": self.decision,
            "final_status": self.final_status,
            "attempts": self.attempts,
            "expires_at": iso(self.expires_at),
            "verified_at": iso(self.verified_at),
            "verified_device_id": self.verified_device_id,
            "verified_ip": self.verified_ip,
            "txn_id": self.txn_id,
            "created_at": iso(self.created_at),
        }
