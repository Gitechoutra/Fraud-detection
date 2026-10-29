from datetime import datetime

from portal.extensions import db
from portal.models.types import DT, MONEY

TXN_STATUSES = ("PENDING", "APPROVED", "REVIEW", "BLOCKED")
# What happened to the money (services/funds.py). NULL for payments that
# move no money (seed history, evaluations).
FUNDS_STATUSES = ("DEBITED", "HELD", "PAID_AFTER_REVIEW", "RELEASED", "NOT_MOVED")
CHANNELS = ("CARD", "UPI", "NETBANKING", "ATM")


class Transaction(db.Model):
    __tablename__ = "transactions"
    __table_args__ = (
        db.Index("ix_txn_account_time", "account_id", "txn_time"),
        db.Index("ix_txn_status_time", "status", "txn_time"),
        db.Index("ix_txn_account_city_time", "account_id", "city", "txn_time"),
        db.Index("ix_txn_time", "txn_time"),
    )

    id = db.Column(db.BigInteger, primary_key=True)
    external_ref = db.Column(db.String(64), unique=True, nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    merchant_id = db.Column(db.Integer, db.ForeignKey("merchants.id"))
    beneficiary_id = db.Column(db.Integer, db.ForeignKey("beneficiaries.id"))
    otp_request_id = db.Column(db.BigInteger, db.ForeignKey("otp_requests.id"))
    amount = db.Column(MONEY, nullable=False)
    currency = db.Column(db.String(3), nullable=False, default="INR")
    channel = db.Column(db.Enum(*CHANNELS, name="txn_channel"), nullable=False)
    city = db.Column(db.String(64))
    device_id = db.Column(db.String(64))
    ip_address = db.Column(db.String(45))
    txn_time = db.Column(DT, nullable=False, default=datetime.now)
    risk_score = db.Column(db.SmallInteger, nullable=False, default=0)
    status = db.Column(db.Enum(*TXN_STATUSES, name="txn_status"), nullable=False, default="PENDING")
    decision_ms = db.Column(db.Numeric(10, 2))
    funds_status = db.Column(db.Enum(*FUNDS_STATUSES, name="txn_funds_status"))
    stage_timings = db.Column(db.JSON)
    # Hook for an external ML model: its 0-100 score, and the points it added
    # (MODEL_SCORE_WEIGHT % of it, only on top of at least one fired rule).
    model_score = db.Column(db.SmallInteger)
    model_points = db.Column(db.SmallInteger)
    is_fraud_label = db.Column(db.Boolean)
    scenario = db.Column(db.String(16))
    # API / SIMULATOR / EVALUATION / SEED / BANK_DEMO / CSV
    source = db.Column(db.String(16), nullable=False, default="API")
    created_at = db.Column(DT, nullable=False, default=datetime.now)
