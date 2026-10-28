from datetime import datetime

from portal.extensions import db
from portal.models.types import DT, iso


class Device(db.Model):
    __tablename__ = "devices"
    __table_args__ = (
        db.UniqueConstraint("account_id", "device_id", name="uq_devices_account_device"),
    )

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    device_id = db.Column(db.String(64), nullable=False)
    device_label = db.Column(db.String(120))
    first_seen = db.Column(DT, nullable=False, default=datetime.now)
    last_seen = db.Column(DT, nullable=False, default=datetime.now)
    is_trusted = db.Column(db.Boolean, nullable=False, default=False)

    def to_dict(self):
        return {
            "id": self.id,
            "account_id": self.account_id,
            "device_id": self.device_id,
            "device_label": self.device_label,
            "first_seen": iso(self.first_seen),
            "last_seen": iso(self.last_seen),
            "is_trusted": self.is_trusted,
        }
