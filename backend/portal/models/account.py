from portal.extensions import db
from portal.models.types import DT, MONEY, iso


class Account(db.Model):
    __tablename__ = "accounts"

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False, index=True)
    account_no = db.Column(db.String(20), unique=True, nullable=False)
    account_type = db.Column(db.String(16), nullable=False, default="SAVINGS")
    opened_on = db.Column(db.Date, nullable=False)
    last_txn_at = db.Column(DT)
    status = db.Column(db.String(16), nullable=False, default="ACTIVE")  # ACTIVE / DORMANT / FROZEN
    balance = db.Column(MONEY, nullable=False, default=0)

    customer = db.relationship("Customer", back_populates="accounts")

    def to_dict(self):
        return {
            "id": self.id,
            "customer_id": self.customer_id,
            "account_no": self.account_no,
            "account_type": self.account_type,
            "opened_on": iso(self.opened_on),
            "last_txn_at": iso(self.last_txn_at),
            "status": self.status,
            "balance": float(self.balance or 0),
        }
