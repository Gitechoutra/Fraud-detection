from datetime import datetime

from portal.extensions import db
from portal.models.types import DT, iso


class MetricRun(db.Model):
    """One evaluation run over a fresh labelled synthetic data set."""

    __tablename__ = "metric_runs"

    id = db.Column(db.Integer, primary_key=True)
    run_at = db.Column(DT, nullable=False, default=datetime.now)
    total = db.Column(db.Integer, nullable=False)
    tp = db.Column(db.Integer, nullable=False)
    fp = db.Column(db.Integer, nullable=False)
    tn = db.Column(db.Integer, nullable=False)
    fn = db.Column(db.Integer, nullable=False)
    precision_v = db.Column(db.Numeric(6, 4), nullable=False)
    recall_v = db.Column(db.Numeric(6, 4), nullable=False)
    f1 = db.Column(db.Numeric(6, 4), nullable=False)
    fpr = db.Column(db.Numeric(6, 4), nullable=False)
    p50_ms = db.Column(db.Numeric(10, 2), nullable=False)
    p95_ms = db.Column(db.Numeric(10, 2), nullable=False)
    tps = db.Column(db.Numeric(10, 2), nullable=False)
    fraud_ratio = db.Column(db.Numeric(5, 4))
    mode = db.Column(db.String(16))  # API / IN_PROCESS / BENCH_INDEXED / BENCH_NO_INDEX
    # Share of flagged payments that list at least one fired rule.
    explainability = db.Column(db.Numeric(6, 4))
    # Worst case from payment received to alert on screen (p95 decision +
    # alert-queue read + the Alerts page polling interval).
    alert_visible_ms = db.Column(db.Numeric(10, 2))
    per_rule_json = db.Column(db.JSON)
    per_scenario_json = db.Column(db.JSON)

    def to_dict(self):
        return {
            "id": self.id,
            "run_at": iso(self.run_at),
            "total": self.total,
            "tp": self.tp,
            "fp": self.fp,
            "tn": self.tn,
            "fn": self.fn,
            "precision": float(self.precision_v),
            "recall": float(self.recall_v),
            "f1": float(self.f1),
            "fpr": float(self.fpr),
            "p50_ms": float(self.p50_ms),
            "p95_ms": float(self.p95_ms),
            "tps": float(self.tps),
            "fraud_ratio": float(self.fraud_ratio) if self.fraud_ratio is not None else None,
            "mode": self.mode,
            "explainability": float(self.explainability) if self.explainability is not None else None,
            "alert_visible_ms": float(self.alert_visible_ms) if self.alert_visible_ms is not None else None,
            "per_rule": self.per_rule_json or [],
            "per_scenario": self.per_scenario_json or [],
        }


class DailyStat(db.Model):
    """Per-day totals, refreshed from v_daily_stats every 5 minutes by the
    scheduler so the dashboard's long-range charts stay cheap."""

    __tablename__ = "daily_stats"

    stat_date = db.Column(db.Date, primary_key=True)
    total = db.Column(db.Integer, nullable=False, default=0)
    approved = db.Column(db.Integer, nullable=False, default=0)
    review = db.Column(db.Integer, nullable=False, default=0)
    blocked = db.Column(db.Integer, nullable=False, default=0)
    total_amount = db.Column(db.Numeric(16, 2), nullable=False, default=0)
    blocked_amount = db.Column(db.Numeric(16, 2), nullable=False, default=0)
    avg_decision_ms = db.Column(db.Numeric(10, 2))
    refreshed_at = db.Column(DT, nullable=False, default=datetime.now)
