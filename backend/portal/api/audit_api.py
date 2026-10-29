"""Audit log (read only): rule changes, watchlist edits, case outcomes, logins."""

from flask import Blueprint, request

from portal.helpers.auth_helpers import min_role
from portal.helpers.responses import ok, page_args, paginated
from portal.models import AuditLog
from portal.services import audit_chain

audit_bp = Blueprint("audit", __name__, url_prefix="/audit")


@audit_bp.get("")
@min_role("RISK_MANAGER")
def list_audit():
    page, per_page, offset = page_args(50)
    query = AuditLog.query
    for arg, column in (("entity", AuditLog.entity), ("actor", AuditLog.actor), ("action", AuditLog.action)):
        if request.args.get(arg):
            query = query.filter(column == request.args[arg])
    if request.args.get("search"):
        q = f"%{request.args['search'].strip()}%"
        query = query.filter(AuditLog.actor.like(q) | AuditLog.action.like(q) | AuditLog.entity_id.like(q))
    total = query.count()
    rows = query.order_by(AuditLog.logged_at.desc(), AuditLog.id.desc()).offset(offset).limit(per_page).all()
    return paginated([r.to_dict() for r in rows], total, page, per_page)


@audit_bp.get("/verify")
@min_role("RISK_MANAGER")
def verify_audit():
    """Re-computes the hash chain: proves no audit entry was changed or removed."""
    return ok(audit_chain.verify())
