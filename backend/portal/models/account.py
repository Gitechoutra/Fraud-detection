from portal.extensions import db
from portal.models.types import DT, MONEY, iso


class Account(db.Model):
    __tablename__ = "accounts"
    __table_args__ = (
        db.CheckConstraint("balance >= 0", name="ck_accounts_balance_not_negative"),
        db.CheckConstraint("held_amount >= 0 AND held_amount <= balance", name="ck_accounts_held_within_balance"),
    )

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False, index=True)
    account_no = db.Column(db.String(20), unique=True, nullable=False)
    account_type = db.Column(db.String(16), nullable=False, default="SAVINGS")
    opened_on = db.Column(db.Date, nullable=False)
    last_txn_at = db.Column(DT)
    status = db.Column(db.String(16), nullable=False, default="ACTIVE")  # ACTIVE / DORMANT / FROZEN
    balance = db.Column(MONEY, nullable=False, default=0)
    # Money reserved for payments held for review (never more than balance;
    # the database enforces both with CHECK constraints).
    held_amount = db.Column(MONEY, nullable=False, default=0, server_default="0")
    # Set when rule R9 fires: until then OTP Shield sends every request from
    # an untrusted device to the registered phone for approval.
    step_up_until = db.Column(DT)

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
            "held_amount": float(self.held_amount or 0),
            "available": float((self.balance or 0) - (self.held_amount or 0)),
            "step_up_until": iso(self.step_up_until),
        }
