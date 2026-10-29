from datetime import datetime

from portal.extensions import db
from portal.models.types import DT, MONEY, iso


class FraudRule(db.Model):
    """One of the nine SQL rules. The stored procedure reads params and
    weight from here on every evaluation, so edits apply immediately."""

    __tablename__ = "fraud_rules"

    rule_code = db.Column(db.String(4), primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    simple_name = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(500), nullable=False)
    simple_explanation = db.Column(db.String(500), nullable=False)
    param_1 = db.Column(MONEY)
    param_2 = db.Column(MONEY)
    param_3 = db.Column(MONEY)
    param_4 = db.Column(MONEY)
    param_labels = db.Column(db.JSON)
    weight = db.Column(db.SmallInteger, nullable=False)
    # The starting weight from the specification (Table 4.4), kept beside
    # the tuned `weight` so the change stays traceable.
    spec_weight = db.Column(db.SmallInteger)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    sort_order = db.Column(db.SmallInteger, nullable=False, default=0)
    updated_by = db.Column(db.String(64))
    updated_at = db.Column(DT, nullable=False, default=datetime.now, onupdate=datetime.now)

    def params(self):
        return [
            None if v is None else float(v)
            for v in (self.param_1, self.param_2, self.param_3, self.param_4)
        ]

    def to_dict(self):
        return {
            "rule_code": self.rule_code,
            "name": self.name,
            "simple_name": self.simple_name,
            "description": self.description,
            "simple_explanation": self.simple_explanation,
            "params": self.params(),
            "param_labels": self.param_labels or [],
            "weight": self.weight,
            "spec_weight": self.spec_weight,
            "is_active": self.is_active,
            "updated_by": self.updated_by,
            "updated_at": iso(self.updated_at),
        }


class SystemSetting(db.Model):
    """Key/value settings read by the stored procedure (decision bands)."""

    __tablename__ = "system_settings"

    setting_key = db.Column(db.String(64), primary_key=True)
    setting_value = db.Column(db.String(255), nullable=False)
    description = db.Column(db.String(255))
    updated_by = db.Column(db.String(64))
    updated_at = db.Column(DT, nullable=False, default=datetime.now, onupdate=datetime.now)
