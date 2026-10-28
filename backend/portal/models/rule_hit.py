from portal.extensions import db
from portal.models.types import DT, iso


class RuleHit(db.Model):
    """Evidence: one row per rule that fired on a transaction."""

    __tablename__ = "rule_hits"
    __table_args__ = (db.Index("ix_rule_hits_txn", "txn_id"),)

    id = db.Column(db.BigInteger, primary_key=True)
    txn_id = db.Column(db.BigInteger, db.ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False)
    rule_code = db.Column(db.String(4), db.ForeignKey("fraud_rules.rule_code"), nullable=False)
    weight_applied = db.Column(db.SmallInteger, nullable=False)
    observed_value = db.Column(db.String(64))
    detail_text = db.Column(db.String(255))
    hit_at = db.Column(DT, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "txn_id": self.txn_id,
            "rule_code": self.rule_code,
            "weight_applied": self.weight_applied,
            "observed_value": self.observed_value,
            "detail_text": self.detail_text,
            "hit_at": iso(self.hit_at),
        }
