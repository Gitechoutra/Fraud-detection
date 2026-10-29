"""KPIs and chart data for the dashboard."""

from datetime import date, datetime, timedelta

from flask import Blueprint, request

from portal.helpers.auth_helpers import min_role
from portal.helpers.db_helpers import fetch_all, fetch_one, jsonable
from portal.helpers.responses import AppError, ok

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")

RANGES = {"today": 0, "7d": 6, "30d": 29, "90d": 89}

_RATE_COLUMNS = """COUNT(*) AS total, SUM(t.status IN ('REVIEW', 'BLOCKED')) AS flagged,
               SUM(t.status = 'BLOCKED') AS blocked,
               COALESCE(SUM(c.outcome = 'CONFIRMED_FRAUD'), 0) AS confirmed_fraud"""
_CASE_JOIN = "LEFT JOIN alerts a ON a.txn_id = t.id LEFT JOIN cases c ON c.alert_id = a.id"


def _start():
    key = request.args.get("range", "today")
    if key not in RANGES:
        raise AppError("range must be one of today, 7d, 30d, 90d.", "BAD_REQUEST", 400)
    return key, datetime.combine(date.today() - timedelta(days=RANGES[key]), datetime.min.time())


@dashboard_bp.get("/summary")
@min_role("ANALYST")
def summary():
    key, start = _start()
    row = fetch_one(
        f"""
        SELECT COUNT(*) AS total,
               COALESCE(SUM(t.status = 'APPROVED'), 0) AS approved,
               COALESCE(SUM(t.status = 'REVIEW'), 0)   AS review,
               COALESCE(SUM(t.status = 'BLOCKED'), 0)  AS blocked,
               COALESCE(SUM(CASE WHEN t.status = 'BLOCKED' THEN t.amount END), 0) AS money_protected,
               COALESCE(SUM(CASE WHEN t.status = 'REVIEW' THEN t.amount END), 0)  AS money_held,
               COALESCE(SUM(t.amount), 0) AS total_amount,
               COALESCE(SUM(c.outcome = 'CONFIRMED_FRAUD'), 0) AS confirmed_fraud,
               ROUND(AVG(t.decision_ms), 2) AS avg_decision_ms,
               MAX(t.decision_ms) AS max_decision_ms
          FROM transactions t {_CASE_JOIN}
         WHERE t.txn_time >= :start AND t.status <> 'PENDING'
        """,
        {"start": start},
    )
    alerts = fetch_one(
        "SELECT COALESCE(SUM(alert_status = 'OPEN'), 0) AS open_alerts, "
        "COALESCE(SUM(alert_status = 'IN_PROGRESS'), 0) AS in_progress, "
        "COALESCE(SUM(alert_status <> 'CLOSED' AND priority = 'HIGH'), 0) AS high_open FROM alerts"
    )
    data = jsonable(row)
    data.update(jsonable(alerts))
    data["range"] = key
    data["flag_rate"] = round((data["review"] + data["blocked"]) / data["total"], 4) if data["total"] else 0
    data["fraud_rate"] = round(data["confirmed_fraud"] / data["total"], 4) if data["total"] else 0
    return ok(data)


@dashboard_bp.get("/charts")
@min_role("ANALYST")
def charts():
    key, start = _start()
    params = {"start": start}
    if key == "today":
        volume = fetch_all(
            """
            SELECT DATE_FORMAT(txn_time, '%H:00') AS label, COUNT(*) AS total,
                   SUM(status = 'APPROVED') AS approved, SUM(status = 'REVIEW') AS review,
                   SUM(status = 'BLOCKED') AS blocked
              FROM transactions WHERE txn_time >= :start AND status <> 'PENDING'
             GROUP BY DATE_FORMAT(txn_time, '%H:00') ORDER BY label
            """,
            params,
        )
    else:
        volume = fetch_all(
            """
            SELECT DATE_FORMAT(stat_date, '%d %b') AS label, total, approved, review, blocked
              FROM daily_stats WHERE stat_date >= DATE(:start) ORDER BY stat_date
            """,
            params,
        )
    decisions = fetch_all(
        "SELECT status, COUNT(*) AS value FROM transactions "
        "WHERE txn_time >= :start AND status <> 'PENDING' GROUP BY status",
        params,
    )
    # Alert rate = held or blocked; fraud rate = confirmed as fraud by an
    # analyst closing the case.
    by_channel = fetch_all(
        f"""
        SELECT t.channel, {_RATE_COLUMNS}
          FROM transactions t {_CASE_JOIN}
         WHERE t.txn_time >= :start AND t.status <> 'PENDING'
         GROUP BY t.channel ORDER BY t.channel
        """,
        params,
    )
    cities = fetch_all(
        f"""
        SELECT t.city, {_RATE_COLUMNS}
          FROM transactions t {_CASE_JOIN}
         WHERE t.txn_time >= :start AND t.status <> 'PENDING' AND t.city IS NOT NULL
         GROUP BY t.city ORDER BY total DESC LIMIT 12
        """,
        params,
    )
    rule_hits = fetch_all(
        """
        SELECT r.rule_code, r.simple_name, COUNT(rh.id) AS hits
          FROM fraud_rules r
          LEFT JOIN rule_hits rh ON rh.rule_code = r.rule_code AND rh.hit_at >= :start
         GROUP BY r.rule_code, r.simple_name, r.sort_order ORDER BY r.sort_order
        """,
        params,
    )
    precision = fetch_all("SELECT * FROM v_rule_precision")
    return ok({
        "range": key,
        "volume": [jsonable(r) for r in volume],
        "decisions": [jsonable(r) for r in decisions],
        "by_channel": [jsonable(r) for r in by_channel],
        "cities": [jsonable(r) for r in cities],
        "rule_hits": [jsonable(r) for r in rule_hits],
        "rule_precision": [jsonable(r) for r in precision],
    })
