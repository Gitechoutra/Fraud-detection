from datetime import datetime

from portal.extensions import db
from portal.models.types import DT, iso


class DeviceApproval(db.Model):
    """'Was this you?' request sent to the customer's trusted device instead
    of an OTP, when the OTP Shield risk is high."""

    __tablename__ = "device_approvals"

    id = db.Column(db.BigInteger, primary_key=True)
    otp_request_id = db.Column(
        db.BigInteger, db.ForeignKey("otp_requests.id", ondelete="CASCADE"), nullable=False
    )
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    status = db.Column(
        db.Enum("PENDING", "APPROVED", "DENIED", "EXPIRED", name="approval_status"),
        nullable=False,
        default="PENDING",
    )
    expires_at = db.Column(DT, nullable=False)
    created_at = db.Column(DT, nullable=False, default=datetime.now)
    responded_at = db.Column(DT)
    responded_device_id = db.Column(db.String(64))

    def to_dict(self):
        return {
            "id": self.id,
            "otp_request_id": self.otp_request_id,
            "account_id": self.account_id,
            "status": self.status,
            "expires_at": iso(self.expires_at),
            "created_at": iso(self.created_at),
            "responded_at": iso(self.responded_at),
            "responded_device_id": self.responded_device_id,
        }
