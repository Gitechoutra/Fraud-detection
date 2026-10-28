from datetime import datetime

from portal.extensions import db
from portal.models.types import DT


class Case(db.Model):
    __tablename__ = "cases"

    id = db.Column(db.BigInteger, primary_key=True)
    alert_id = db.Column(
        db.BigInteger, db.ForeignKey("alerts.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    analyst_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    outcome = db.Column(db.Enum("CONFIRMED_FRAUD", "FALSE_POSITIVE", name="case_outcome"))
    notes = db.Column(db.Text)
    created_at = db.Column(DT, nullable=False, default=datetime.now)
    closed_at = db.Column(DT)


class CaseNote(db.Model):
    __tablename__ = "case_notes"

    id = db.Column(db.BigInteger, primary_key=True)
    case_id = db.Column(
        db.BigInteger, db.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(DT, nullable=False, default=datetime.now)
