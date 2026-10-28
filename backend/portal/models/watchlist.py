from datetime import datetime

from portal.extensions import db
from portal.models.types import DT, iso

WATCHLIST_TYPES = ("IP", "DEVICE", "ACCOUNT", "MERCHANT")


class WatchlistEntry(db.Model):
    __tablename__ = "watchlist"
    __table_args__ = (
        db.UniqueConstraint("entry_type", "entry_value", name="uq_watchlist_type_value"),
    )

    id = db.Column(db.Integer, primary_key=True)
    entry_type = db.Column(db.Enum(*WATCHLIST_TYPES, name="watchlist_type"), nullable=False)
    entry_value = db.Column(db.String(128), nullable=False)
    reason = db.Column(db.String(255), nullable=False)
    added_by = db.Column(db.String(64), nullable=False)
    added_at = db.Column(DT, nullable=False, default=datetime.now)

    def to_dict(self):
        return {
            "id": self.id,
            "entry_type": self.entry_type,
            "entry_value": self.entry_value,
            "reason": self.reason,
            "added_by": self.added_by,
            "added_at": iso(self.added_at),
        }
