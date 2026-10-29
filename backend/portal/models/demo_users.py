"""Customer-app logins, the demo fraudsters and what they stole, and the
alerts shown in the customer's banking app.

The fraudster tables exist only for the clearly-labelled local simulation
(/attacker): a fraudster can act only through the credentials linked to
their account, and every payment they attempt goes through the normal
fraud engine.
"""

from datetime import datetime

from portal.extensions import db
from portal.models.types import DT, iso

OBTAINED_VIA = ("PHISHING_LINK", "OTP_CALL", "CARD_SKIMMING", "SIM_SWAP")
ALERT_SEVERITIES = ("INFO", "WARNING", "DANGER")
ALERT_ACTIONS = ("PENDING", "CONFIRMED_ME", "REPORTED_NOT_ME")


class CustomerUser(db.Model):
    """Login for the customer banking app (/bank)."""

    __tablename__ = "customer_users"

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, unique=True)
    username = db.Column(db.String(64), nullable=False, unique=True)
    password_hash = db.Column(db.String(128), nullable=False)
    is_locked = db.Column(db.Boolean, nullable=False, default=False)
    failed_logins = db.Column(db.SmallInteger, nullable=False, default=0)
    card_last4 = db.Column(db.String(4))
    # Tokens issued before this moment are refused (logout everywhere).
    tokens_valid_after = db.Column(DT)
    created_at = db.Column(DT, nullable=False, default=datetime.now)
    last_login_at = db.Column(DT)


class FraudsterUser(db.Model):
    """A simulated fraudster for the /attacker demo console."""

    __tablename__ = "fraudster_users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), nullable=False, unique=True)
    password_hash = db.Column(db.String(128), nullable=False)
    display_name = db.Column(db.String(120), nullable=False)
    base_city = db.Column(db.String(64), nullable=False)
    # Set when a victim reports "Not me": the fraudster's open sessions end.
    tokens_valid_after = db.Column(DT)
    created_at = db.Column(DT, nullable=False, default=datetime.now)


class StolenCredential(db.Model):
    """Which customer's credentials a fraudster holds, and how they got them."""

    __tablename__ = "stolen_credentials"
    __table_args__ = (db.UniqueConstraint("fraudster_id", "customer_id", name="uq_stolen_fraudster_customer"),)

    id = db.Column(db.Integer, primary_key=True)
    fraudster_id = db.Column(db.Integer, db.ForeignKey("fraudster_users.id", ondelete="CASCADE"), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    obtained_via = db.Column(db.Enum(*OBTAINED_VIA, name="obtained_via"), nullable=False)
    obtained_at = db.Column(DT, nullable=False, default=datetime.now)


class CustomerAlert(db.Model):
    """A fraud alert in the customer's banking app, with their answer."""

    __tablename__ = "customer_alerts"
    __table_args__ = (
        db.Index("ix_customer_alerts_customer_id", "customer_id", "id"),
        db.UniqueConstraint("txn_id", "severity", name="uq_customer_alerts_txn_severity"),
    )

    id = db.Column(db.BigInteger, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    txn_id = db.Column(db.BigInteger, db.ForeignKey("transactions.id", ondelete="CASCADE"))
    severity = db.Column(db.Enum(*ALERT_SEVERITIES, name="customer_alert_severity"), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    body = db.Column(db.String(500), nullable=False)
    action_status = db.Column(db.Enum(*ALERT_ACTIONS, name="customer_alert_action"), nullable=False, default="PENDING")
    created_at = db.Column(DT, nullable=False, default=datetime.now)
    responded_at = db.Column(DT)
    read_at = db.Column(DT)


class AttackEvent(db.Model):
    """Links each simulated attack payment to the fraudster who made it, so a
    "Not me" report can be traced server-side (never from client input)."""

    __tablename__ = "attack_events"
    __table_args__ = (db.Index("ix_attack_events_fraudster", "fraudster_id", "id"),)

    id = db.Column(db.BigInteger, primary_key=True)
    fraudster_id = db.Column(db.Integer, db.ForeignKey("fraudster_users.id", ondelete="CASCADE"), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    txn_id = db.Column(db.BigInteger, db.ForeignKey("transactions.id", ondelete="CASCADE"), unique=True)
    scenario = db.Column(db.String(16), nullable=False)
    step = db.Column(db.String(160))
    created_at = db.Column(DT, nullable=False, default=datetime.now)


def alert_dict(a, extra=None):
    out = {
        "id": a.id,
        "txn_id": a.txn_id,
        "severity": a.severity,
        "title": a.title,
        "body": a.body,
        "action_status": a.action_status,
        "created_at": iso(a.created_at),
        "responded_at": iso(a.responded_at),
        "read": a.read_at is not None,
    }
    out.update(extra or {})
    return out
