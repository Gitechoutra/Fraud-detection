"""Watchlist of known-bad IPs, devices, accounts and merchants (rule R6)."""

from flask import Blueprint, request

from portal.extensions import db
from portal.helpers.auth_helpers import current_user, min_role
from portal.helpers.db_helpers import set_actor
from portal.helpers.responses import AppError, ok, page_args, paginated
from portal.helpers.validators import WatchlistSchema, load
from portal.models import WatchlistEntry

watchlist_bp = Blueprint("watchlist", __name__, url_prefix="/watchlist")


@watchlist_bp.get("")
@min_role("ANALYST")
def list_entries():
    page, per_page, offset = page_args(50)
    query = WatchlistEntry.query
    if request.args.get("type"):
        query = query.filter(WatchlistEntry.entry_type == request.args["type"].upper())
    if request.args.get("search"):
        q = f"%{request.args['search'].strip()}%"
        query = query.filter(WatchlistEntry.entry_value.like(q) | WatchlistEntry.reason.like(q))
    total = query.count()
    rows = query.order_by(WatchlistEntry.added_at.desc()).offset(offset).limit(per_page).all()
    return paginated([r.to_dict() for r in rows], total, page, per_page)


@watchlist_bp.post("")
@min_role("RISK_MANAGER")
def add_entry():
    data = load(WatchlistSchema, request.get_json(silent=True))
    value = data["entry_value"].strip()
    if WatchlistEntry.query.filter_by(entry_type=data["entry_type"], entry_value=value).first():
        raise AppError("That entry is already on the watchlist.", "DUPLICATE", 409)
    me = current_user()
    set_actor(me.username)
    entry = WatchlistEntry(entry_type=data["entry_type"], entry_value=value, reason=data["reason"].strip(),
                           added_by=me.username)
    db.session.add(entry)
    db.session.commit()
    return ok(entry.to_dict(), 201)


@watchlist_bp.delete("/<int:entry_id>")
@min_role("RISK_MANAGER")
def delete_entry(entry_id):
    entry = db.session.get(WatchlistEntry, entry_id)
    if entry is None:
        raise AppError("We couldn't find that entry.", "NOT_FOUND", 404)
    set_actor(current_user().username)
    db.session.delete(entry)
    db.session.commit()
    return ok({"deleted": entry_id})
