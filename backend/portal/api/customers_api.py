"""Customers with their accounts, devices, payees and security events (read only)."""

from flask import Blueprint, request

from portal.extensions import db
from portal.helpers.auth_helpers import min_role
from portal.helpers.db_helpers import fetch_all, jsonable, scalar
from portal.helpers.responses import AppError, ok, page_args, paginated
from portal.models import Account, Beneficiary, Customer, Device, SessionEvent

customers_bp = Blueprint("customers", __name__, url_prefix="/customers")


@customers_bp.get("")
@min_role("ANALYST")
def list_customers():
    page, per_page, offset = page_args()
    where, params = "1 = 1", {}
    if request.args.get("search"):
        where = "(c.name LIKE :q OR c.phone LIKE :q OR c.home_city LIKE :q OR a.account_no LIKE :q)"
        params["q"] = f"%{request.args['search'].strip()}%"
    total = scalar(
        f"SELECT COUNT(DISTINCT c.id) FROM customers c LEFT JOIN accounts a ON a.customer_id = c.id WHERE {where}",
        params,
    )
    rows = fetch_all(
        f"""
        SELECT c.id, c.name, c.phone, c.home_city, c.kyc_status, c.typical_amount,
               COUNT(DISTINCT a.id) AS accounts,
               GROUP_CONCAT(DISTINCT a.account_no) AS account_nos,
               MAX(a.last_txn_at) AS last_txn_at,
               SUM(a.status = 'DORMANT') AS dormant_accounts
          FROM customers c LEFT JOIN accounts a ON a.customer_id = c.id
         WHERE {where}
         GROUP BY c.id ORDER BY c.name LIMIT :limit OFFSET :offset
        """,
        {**params, "limit": per_page, "offset": offset},
    )
    return paginated([jsonable(r) for r in rows], total, page, per_page)


@customers_bp.get("/<int:customer_id>")
@min_role("ANALYST")
def get_customer(customer_id):
    customer = db.session.get(Customer, customer_id)
    if customer is None:
        raise AppError("We couldn't find that customer.", "NOT_FOUND", 404)
    accounts = Account.query.filter_by(customer_id=customer.id).all()
    ids = [a.id for a in accounts] or [0]
    devices = Device.query.filter(Device.account_id.in_(ids)).order_by(Device.last_seen.desc()).all()
    payees = Beneficiary.query.filter(Beneficiary.account_id.in_(ids)).order_by(Beneficiary.added_at.desc()).all()
    sessions = (
        SessionEvent.query.filter(SessionEvent.account_id.in_(ids))
        .order_by(SessionEvent.created_at.desc()).limit(30).all()
    )
    placeholders = ", ".join(f":a{i}" for i in range(len(ids)))
    recent = fetch_all(
        "SELECT id, account_id, txn_time, amount, channel, city, status, risk_score FROM transactions "
        f"WHERE account_id IN ({placeholders}) ORDER BY txn_time DESC LIMIT 25",
        {f"a{i}": v for i, v in enumerate(ids)},
    )
    return ok({
        "customer": customer.to_dict(),
        "accounts": [a.to_dict() for a in accounts],
        "devices": [d.to_dict() for d in devices],
        "payees": [p.to_dict() for p in payees],
        "sessions": [s.to_dict() for s in sessions],
        "recent_transactions": [jsonable(r) for r in recent],
    })
