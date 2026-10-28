from datetime import datetime

from portal.extensions import db
from portal.models.types import DT, iso


class Notification(db.Model):
    """Every SMS / in-app message sent to a customer. The demo "Customer
    phone" screens read from here."""

    __tablename__ = "notifications"
    __table_args__ = (db.Index("ix_notifications_customer_created", "customer_id", "created_at"),)

    id = db.Column(db.BigInteger, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)
    channel = db.Column(db.Enum("SMS", "APP", name="notification_channel"), nullable=False)
    kind = db.Column(db.String(16), nullable=False, default="INFO")  # OTP / APPROVAL / ALERT / INFO
    ref_id = db.Column(db.BigInteger)
    title = db.Column(db.String(120), nullable=False)
    body = db.Column(db.String(500), nullable=False)
    created_at = db.Column(DT, nullable=False, default=datetime.now)
    read_at = db.Column(DT)

    def to_dict(self):
        return {
            "id": self.id,
            "customer_id": self.customer_id,
            "channel": self.channel,
            "kind": self.kind,
            "ref_id": self.ref_id,
            "title": self.title,
            "body": self.body,
            "created_at": iso(self.created_at),
            "read_at": iso(self.read_at),
        }
