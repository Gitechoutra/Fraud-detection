from datetime import datetime

from portal.extensions import db
from portal.models.types import DT, MONEY, iso


class Customer(db.Model):
    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120))
    home_city = db.Column(db.String(64), nullable=False)
    kyc_status = db.Column(db.String(16), nullable=False, default="VERIFIED")
    created_at = db.Column(DT, nullable=False, default=datetime.now)
    # Spending profile, used by the synthetic traffic generator.
    typical_amount = db.Column(MONEY, nullable=False, default=1000)
    active_from_hour = db.Column(db.SmallInteger, nullable=False, default=8)
    active_to_hour = db.Column(db.SmallInteger, nullable=False, default=22)
    usual_channels = db.Column(db.String(64), nullable=False, default="UPI,CARD")
    # Demo bank app login ("net banking").
    netbanking_id = db.Column(db.String(64), unique=True)
    netbanking_password_hash = db.Column(db.String(128))

    accounts = db.relationship("Account", back_populates="customer", lazy="selectin")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "home_city": self.home_city,
            "kyc_status": self.kyc_status,
            "typical_amount": float(self.typical_amount or 0),
            "active_hours": [self.active_from_hour, self.active_to_hour],
            "usual_channels": self.usual_channels.split(",") if self.usual_channels else [],
            "netbanking_id": self.netbanking_id,
            "created_at": iso(self.created_at),
        }
