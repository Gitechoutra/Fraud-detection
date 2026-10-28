"""Column types shared by all models: money is DECIMAL(14,2), times are
DATETIME(3) (millisecond precision, needed to order bursts of payments)."""

from sqlalchemy.dialects import mysql

from portal.extensions import db

DT = mysql.DATETIME(fsp=3)
MONEY = db.Numeric(14, 2)


def iso(value):
    """ISO string for a datetime/date column, or None."""
    return value.isoformat() if value is not None else None
