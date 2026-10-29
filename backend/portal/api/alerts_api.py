"""Alert queue (from v_alert_queue): list, detail, assign, change status,
and the measured dashboard freshness (time from an alert being committed to
it appearing on an analyst's screen)."""

from datetime import datetime

from flask import Blueprint, request
from sqlalchemy import text

from portal.extensions import db
from portal.helpers.auth_helpers import current_user, min_role
from portal.helpers.db_helpers import fetch_all, fetch_one, jsonable, scalar, set_actor
from portal.helpers.responses import AppError, ok, page_args
from portal.helpers.validators import AlertSeenSchema, AlertUpdateSchema, load
from portal.models import Alert, User
from portal.services import evaluator

alerts_bp = Blueprint("alerts", __name__, url_prefix="/alerts")


def _row(r):
    r = jsonable(r)
    r["rule_codes"] = r["rule_codes"].split(",") if r.get("rule_codes") else []
    return r


@alerts_bp.get("")
@min_role("ANALYST")
def list_alerts():
    page, per_page, offset = page_args()
    where, params = ["1 = 1"], {}
    status = request.args.get("status")
    if status and status.upper() != "ALL":
        where.append("alert_status = :status")
        params["status"] = status.upper()
    if request.args.get("priority"):
        where.append("priority = :priority")
        params["priority"] = request.args["priority"].upper()
    if request.args.get("mine") == "1":
        where.append("assigned_to = :me")
        params["me"] = current_user().id
    if request.args.get("search"):
        where.append("(customer_name LIKE :q OR account_no LIKE :q OR summary LIKE :q)")
        params["q"] = f"%{request.args['search'].strip()}%"
    clause = " AND ".join(where)
    total = scalar(f"SELECT COUNT(*) FROM v_alert_queue WHERE {clause}", params)
    rows = fetch_all(
        f"SELECT * FROM v_alert_queue WHERE {clause} "
        "ORDER BY alert_status = 'CLOSED', priority = 'HIGH' DESC, created_at ASC "
        "LIMIT :limit OFFSET :offset",
        {**params, "limit": per_page, "offset": offset},
    )
    counts = {r["alert_status"]: r["n"] for r in fetch_all(
        "SELECT alert_status, COUNT(*) AS n FROM alerts GROUP BY alert_status")}
    # The newest alerts, whatever the filter and page, so the screen can show
    # each new one as soon as it exists.
    newest = fetch_all("SELECT a.id AS alert_id, c.id AS case_id, a.summary, a.priority, a.risk_score, a.created_at "
                       "FROM alerts a LEFT JOIN cases c ON c.alert_id = a.id ORDER BY a.id DESC LIMIT 10")
    return ok({
        "items": [_row(r) for r in rows],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, -(-total // per_page)),
        "counts": {k: counts.get(k, 0) for k in ("OPEN", "IN_PROGRESS", "CLOSED")},
        "newest": [jsonable(r) for r in newest],
    })


@alerts_bp.post("/seen")
@min_role("ANALYST")
def mark_seen():
    """The Alerts page reports alerts it has just displayed for the first
    time; the database clock stamps when (the same clock as created_at)."""
    ids = load(AlertSeenSchema, request.get_json(silent=True))["alert_ids"]
    if ids:
        marks = ", ".join(f":a{i}" for i in range(len(ids)))
        db.session.execute(
            text(f"UPDATE alerts SET first_seen_at = NOW(3) WHERE first_seen_at IS NULL AND id IN ({marks})"),
            {f"a{i}": v for i, v in enumerate(ids)},
        )
        db.session.commit()
    return ok({"marked": len(ids)})


@alerts_bp.get("/freshness")
@min_role("ANALYST")
def freshness():
    """Measured time from an alert being committed to it first appearing on
    screen, over the last `days` days (specification Table 3.1: within 3 s)."""
    days = min(90, max(1, request.args.get("days", 7, type=int)))
    return ok(evaluator.measured_alert_freshness(days))


@alerts_bp.get("/<int:alert_id>")
@min_role("ANALYST")
def get_alert(alert_id):
    row = fetch_one("SELECT * FROM v_alert_queue WHERE alert_id = :id", {"id": alert_id})
    if row is None:
        raise AppError("We couldn't find that alert.", "NOT_FOUND", 404)
    return ok(_row(row))


@alerts_bp.patch("/<int:alert_id>")
@min_role("ANALYST")
def update_alert(alert_id):
    alert = db.session.get(Alert, alert_id)
    if alert is None:
        raise AppError("We couldn't find that alert.", "NOT_FOUND", 404)
    data = load(AlertUpdateSchema, request.get_json(silent=True))
    me = current_user()
    set_actor(me.username)
    if data["assign_to_me"]:
        alert.assigned_to = me.id
        if alert.alert_status == "OPEN":
            alert.alert_status = "IN_PROGRESS"
    elif "assigned_to" in (request.get_json(silent=True) or {}):
        if data["assigned_to"] is not None and db.session.get(User, data["assigned_to"]) is None:
            raise AppError("That user does not exist.", "USER_NOT_FOUND", 404)
        alert.assigned_to = data["assigned_to"]
    if data["alert_status"]:
        alert.alert_status = data["alert_status"]
    alert.updated_at = datetime.now()
    db.session.commit()
    return ok(_row(fetch_one("SELECT * FROM v_alert_queue WHERE alert_id = :id", {"id": alert_id})))
