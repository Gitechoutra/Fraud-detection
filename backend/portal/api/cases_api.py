"""Investigation cases: evidence, timeline, notes and the final outcome."""

import json
from datetime import datetime

from flask import Blueprint, request

from portal.extensions import db
from portal.helpers.auth_helpers import current_user, min_role
from portal.helpers.db_helpers import fetch_all, fetch_one, jsonable, set_actor
from portal.helpers.explain import inr
from portal.helpers.responses import AppError, ok
from portal.helpers.validators import CaseNoteSchema, CaseOutcomeSchema, load
from portal.models import Alert, Case, CaseNote
from portal.services import fraud_engine

cases_bp = Blueprint("cases", __name__, url_prefix="/cases")


def _case_or_404(case_id):
    case = db.session.get(Case, case_id)
    if case is None:
        raise AppError("We couldn't find that case.", "NOT_FOUND", 404)
    return case


def _timeline(case, queue, notes):
    events = []
    if queue.get("txn_time"):
        events.append({"at": queue["txn_time"], "kind": "PAYMENT",
                       "text": f"Payment of {inr(queue['amount'])} received for checking"})
    events.append({"at": queue["created_at"], "kind": "ALERT",
                   "text": f"Alert raised ({queue['priority']} priority, risk {queue['risk_score']}/100)"})
    for row in fetch_all(
        "SELECT actor, action, new_value, logged_at FROM audit_log "
        "WHERE entity = 'cases' AND entity_id = :id ORDER BY logged_at", {"id": str(case.id)}
    ):
        events.append({"at": row["logged_at"].isoformat(), "kind": row["action"],
                       "text": f"{row['actor']}: {row['action'].replace('_', ' ').lower()}"})
    for n in notes:
        events.append({"at": n["created_at"], "kind": "NOTE", "text": f"{n['author']} added a note"})
    if case.closed_at:
        events.append({"at": case.closed_at.isoformat(), "kind": "CLOSED",
                       "text": "Closed as " + ("confirmed fraud" if case.outcome == "CONFIRMED_FRAUD" else "genuine")})
    return sorted(events, key=lambda e: e["at"])


@cases_bp.get("/<int:case_id>")
@min_role("ANALYST")
def get_case(case_id):
    case = _case_or_404(case_id)
    queue = jsonable(fetch_one("SELECT * FROM v_alert_queue WHERE alert_id = :id", {"id": case.alert_id}))
    queue["rule_codes"] = queue["rule_codes"].split(",") if queue.get("rule_codes") else []
    hits = []
    if queue.get("txn_id"):
        hits = [jsonable(h) for h in fetch_all(
            "SELECT rule_code, weight_applied, observed_value, detail_text FROM rule_hits "
            "WHERE txn_id = :id ORDER BY weight_applied DESC", {"id": queue["txn_id"]})]
    otp = None
    if queue.get("otp_request_id"):
        otp = jsonable(fetch_one(
            "SELECT id, amount, requesting_device_id, ip_address, city, risk_points, signals_json, decision, "
            "final_status, created_at FROM otp_requests WHERE id = :id", {"id": queue["otp_request_id"]}))
        if isinstance(otp.get("signals_json"), str):
            otp["signals_json"] = json.loads(otp["signals_json"])
    notes = [jsonable(n) for n in fetch_all(
        "SELECT n.id, n.body, n.created_at, u.full_name AS author FROM case_notes n "
        "JOIN users u ON u.id = n.author_id WHERE n.case_id = :id ORDER BY n.created_at", {"id": case.id})]
    recent = []
    if queue.get("account_id"):
        recent = [jsonable(r) for r in fetch_all(
            "SELECT id, txn_time, amount, status, city, channel, risk_score FROM transactions "
            "WHERE account_id = :a ORDER BY txn_time DESC LIMIT 10", {"a": queue["account_id"]})]
    analyst = fetch_one("SELECT full_name FROM users WHERE id = :id", {"id": case.analyst_id}) if case.analyst_id else None
    return ok({
        "case": {
            "id": case.id,
            "alert_id": case.alert_id,
            "outcome": case.outcome,
            "notes": case.notes,
            "analyst": analyst["full_name"] if analyst else None,
            "created_at": case.created_at.isoformat(),
            "closed_at": case.closed_at.isoformat() if case.closed_at else None,
        },
        "alert": queue,
        "hits": hits,
        "otp_request": otp,
        "notes": notes,
        "recent_transactions": recent,
        "timeline": _timeline(case, queue, notes),
    })


@cases_bp.post("/<int:case_id>/notes")
@min_role("ANALYST")
def add_note(case_id):
    case = _case_or_404(case_id)
    data = load(CaseNoteSchema, request.get_json(silent=True))
    me = current_user()
    note = CaseNote(case_id=case.id, author_id=me.id, body=data["body"].strip(), created_at=datetime.now())
    db.session.add(note)
    db.session.commit()
    return ok({"id": note.id, "body": note.body, "author": me.full_name,
               "created_at": note.created_at.isoformat()}, 201)


@cases_bp.patch("/<int:case_id>/outcome")
@min_role("ANALYST")
def set_outcome(case_id):
    case = _case_or_404(case_id)
    if case.outcome:
        raise AppError("This case is already closed.", "CASE_CLOSED", 409)
    data = load(CaseOutcomeSchema, request.get_json(silent=True))
    me = current_user()
    set_actor(me.username)
    now = datetime.now()
    case.outcome = data["outcome"]
    case.analyst_id = me.id
    case.notes = data.get("notes")
    case.closed_at = now
    alert = db.session.get(Alert, case.alert_id)
    alert.alert_status = "CLOSED"
    alert.assigned_to = alert.assigned_to or me.id
    alert.updated_at = now
    if data.get("notes"):
        db.session.add(CaseNote(case_id=case.id, author_id=me.id, body=data["notes"], created_at=now))
    if case.outcome == "FALSE_POSITIVE" and alert.txn_id:
        # A genuine payment: lift the R9 holds and watchlist entries it caused.
        fraud_engine.r9_release(alert.txn_id)
    db.session.commit()
    return ok({"id": case.id, "outcome": case.outcome, "closed_at": now.isoformat()})
