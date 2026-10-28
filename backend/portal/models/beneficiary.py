from datetime import datetime

from portal.extensions import db
from portal.models.types import DT, iso


class Beneficiary(db.Model):
    """A payee the account holder can send money to."""

    __tablename__ = "beneficiaries"
    __table_args__ = (db.Index("ix_beneficiaries_account_added", "account_id", "added_at"),)

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    payee_name = db.Column(db.String(120), nullable=False)
    payee_account_no = db.Column(db.String(20), nullable=False)
    payee_ifsc = db.Column(db.String(11), nullable=False)
    added_at = db.Column(DT, nullable=False, default=datetime.now)
    added_device_id = db.Column(db.String(64))
    cooling_until = db.Column(DT)

    def to_dict(self):
        return {
            "id": self.id,
            "account_id": self.account_id,
            "payee_name": self.payee_name,
            "payee_account_no": self.payee_account_no,
            "payee_ifsc": self.payee_ifsc,
            "added_at": iso(self.added_at),
            "added_device_id": self.added_device_id,
            "cooling_until": iso(self.cooling_until),
        }
