"""Ingest payments (single + CSV), list them, live feed, and the detail page."""

import csv
import io
import json
import os
from datetime import datetime

from flask import Blueprint, current_app, request
from marshmallow import ValidationError
from werkzeug.utils import secure_filename

from portal.extensions import limiter
from portal.helpers.auth_helpers import api_key_or_role, has_api_key, min_role
from portal.helpers.db_helpers import fetch_all, fetch_one, jsonable, scalar
from portal.helpers.explain import RULE_PLAIN, decision_summary
from portal.helpers.responses import AppError, ok, page_args, paginated
from portal.helpers.timing import now_ms
from portal.helpers.validators import TransactionSchema, load
from portal.models import FraudRule, SystemSetting
from portal.services import fraud_engine

transactions_bp = Blueprint("transactions", __name__, url_prefix="/transactions")

MAX_CSV_ROWS = 5000

ROW_SELECT = """
SELECT t.id, t.external_ref, t.amount, t.channel, t.city, t.device_id, t.ip_address, t.txn_time,
       t.risk_score, t.status, t.decision_ms, t.scenario, t.source, t.is_fraud_label,
       t.account_id, a.account_no, c.id AS customer_id, c.name AS customer_name,
       m.name AS merchant_name, b.payee_name,
       (SELECT GROUP_CONCAT(rh.rule_code ORDER BY rh.rule_code) FROM rule_hits rh
         WHERE rh.txn_id = t.id) AS rule_codes
  FROM transactions t
  JOIN accounts a        ON a.id = t.account_id
  JOIN customers c       ON c.id = a.customer_id
  LEFT JOIN merchants m  ON m.id = t.merchant_id
  LEFT JOIN beneficiaries b ON b.id = t.beneficiary_id
"""


def _json(value):
    return json.loads(value) if isinstance(value, (str, bytes)) else value


def _row(r):
    r = jsonable(r)
    r["rule_codes"] = r["rule_codes"].split(",") if r.get("rule_codes") else []
    return r


def bands():
    values = {s.setting_key: int(s.setting_value) for s in SystemSetting.query.all()}
    return values.get("REVIEW_THRESHOLD", 40), values.get("BLOCK_THRESHOLD", 70)


@transactions_bp.post("")
@limiter.limit("1200 per minute", exempt_when=has_api_key)
@api_key_or_role("ADMIN")
def ingest():
    t_received = now_ms()
    payload = load(TransactionSchema, request.get_json(silent=True))
    result = fraud_engine.ingest(payload, source=payload.get("source") or "API", t_received=t_received)
    return ok(result, 200 if result["duplicate"] else 201)


@transactions_bp.post("/bulk")
@api_key_or_role("ADMIN")
def bulk_upload():
    """CSV columns: external_ref, account_no (or account_id), amount, channel,
    and optionally city, device_id, ip_address, merchant_id, txn_time."""
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        raise AppError("Choose a CSV file to upload.", "NO_FILE", 400)
    if not upload.filename.lower().endswith(".csv"):
        raise AppError("Only .csv files are accepted.", "BAD_FILE_TYPE", 400)
    raw = upload.read()
    name = f"{datetime.now():%Y%m%d_%H%M%S}_{secure_filename(upload.filename)}"
    with open(os.path.join(current_app.config["UPLOAD_FOLDER"], name), "wb") as fh:
        fh.write(raw)

    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    summary = {"file": name, "rows": 0, "approved": 0, "review": 0, "blocked": 0, "duplicates": 0, "errors": []}
    schema = TransactionSchema()
    for line_no, row in enumerate(reader, start=2):
        if summary["rows"] >= MAX_CSV_ROWS:
            summary["errors"].append({"line": line_no, "error": f"Stopped after {MAX_CSV_ROWS} rows."})
            break
        summary["rows"] += 1
        clean = {k.strip(): v.strip() for k, v in row.items() if k and v not in (None, "")}
        try:
            payload = schema.load(clean)
            result = fraud_engine.ingest(payload, source="CSV")
        except ValidationError as exc:
            summary["errors"].append({"line": line_no, "error": exc.messages})
            continue
        except AppError as exc:
            summary["errors"].append({"line": line_no, "error": exc.message})
            continue
        if result["duplicate"]:
            summary["duplicates"] += 1
        else:
            summary[result["status"].lower()] += 1
    return ok(summary)


@transactions_bp.get("")
@min_role("ANALYST")
def list_transactions():
    page, per_page, offset = page_args()
    where, params = ["1 = 1"], {}
    args = request.args
    if args.get("status"):
        where.append("t.status = :status")
        params["status"] = args["status"].upper()
    if args.get("channel"):
        where.append("t.channel = :channel")
        params["channel"] = args["channel"].upper()
    if args.get("source"):
        where.append("t.source = :source")
        params["source"] = args["source"].upper()
    if args.get("date_from"):
        where.append("t.txn_time >= :date_from")
        params["date_from"] = args["date_from"]
    if args.get("date_to"):
        where.append("t.txn_time < DATE_ADD(:date_to, INTERVAL 1 DAY)")
        params["date_to"] = args["date_to"]
    if args.get("min_score"):
        where.append("t.risk_score >= :min_score")
        params["min_score"] = int(args["min_score"])
    if args.get("account_id"):
        where.append("t.account_id = :account_id")
        params["account_id"] = int(args["account_id"])
    if args.get("search"):
        where.append("(t.external_ref LIKE :q OR c.name LIKE :q OR a.account_no LIKE :q OR t.city LIKE :q)")
        params["q"] = f"%{args['search'].strip()}%"
    clause = " AND ".join(where)
    total = scalar(
        f"SELECT COUNT(*) FROM transactions t JOIN accounts a ON a.id = t.account_id "
        f"JOIN customers c ON c.id = a.customer_id WHERE {clause}",
        params,
    )
    rows = fetch_all(
        f"{ROW_SELECT} WHERE {clause} ORDER BY t.id DESC LIMIT :limit OFFSET :offset",
        {**params, "limit": per_page, "offset": offset},
    )
    return paginated([_row(r) for r in rows], total, page, per_page)


@transactions_bp.get("/latest")
@min_role("ANALYST")
def latest():
    """Live feed: everything newer than since_id (oldest first), or the latest 30."""
    limit = min(200, int(request.args.get("limit", 50)))
    since_id = request.args.get("since_id", type=int)
    if since_id:
        rows = fetch_all(
            f"{ROW_SELECT} WHERE t.id > :since AND t.status <> 'PENDING' ORDER BY t.id ASC LIMIT :limit",
            {"since": since_id, "limit": limit},
        )
    else:
        rows = fetch_all(
            f"{ROW_SELECT} WHERE t.status <> 'PENDING' ORDER BY t.id DESC LIMIT :limit",
            {"limit": min(limit, 30)},
        )
        rows.reverse()
    max_id = scalar("SELECT COALESCE(MAX(id), 0) FROM transactions")
    return ok({"items": [_row(r) for r in rows], "max_id": max_id})


@transactions_bp.get("/<int:txn_id>")
@min_role("ANALYST")
def detail(txn_id):
    txn = fetch_one(
        f"""
        SELECT t.*, a.account_no, a.account_type, a.status AS account_status, a.last_txn_at,
               c.id AS customer_id, c.name AS customer_name, c.home_city, c.phone, c.typical_amount,
               m.name AS merchant_name, m.category AS merchant_category, m.city AS merchant_city,
               b.payee_name, b.payee_account_no, b.added_at AS payee_added_at
          FROM transactions t
          JOIN accounts a ON a.id = t.account_id
          JOIN customers c ON c.id = a.customer_id
          LEFT JOIN merchants m ON m.id = t.merchant_id
          LEFT JOIN beneficiaries b ON b.id = t.beneficiary_id
         WHERE t.id = :id
        """,
        {"id": txn_id},
    )
    if txn is None:
        raise AppError("We couldn't find that payment.", "NOT_FOUND", 404)
    hits = [jsonable(h) for h in fetch_all(
        "SELECT rule_code, weight_applied, observed_value, detail_text, hit_at FROM rule_hits "
        "WHERE txn_id = :id ORDER BY weight_applied DESC", {"id": txn_id})]
    fired = {h["rule_code"]: h for h in hits}
    rules = []
    for rule in FraudRule.query.order_by(FraudRule.sort_order).all():
        hit = fired.get(rule.rule_code)
        rules.append({
            "rule_code": rule.rule_code,
            "simple_name": rule.simple_name,
            "simple_explanation": rule.simple_explanation,
            "weight": rule.weight,
            "is_active": rule.is_active,
            "fired": hit is not None,
            "weight_applied": hit["weight_applied"] if hit else 0,
            "observed_value": hit["observed_value"] if hit else None,
            "sentence": hit["detail_text"] if hit else RULE_PLAIN[rule.rule_code],
        })
    review, block = bands()
    alert = fetch_one(
        "SELECT al.id AS alert_id, al.priority, al.alert_status, ca.id AS case_id, ca.outcome "
        "FROM alerts al LEFT JOIN cases ca ON ca.alert_id = al.id WHERE al.txn_id = :id",
        {"id": txn_id},
    )
    history = [jsonable(r) for r in fetch_all(
        "SELECT id, txn_time, amount, status, city, channel FROM transactions "
        "WHERE account_id = :a AND txn_time <= :t ORDER BY txn_time DESC LIMIT 20",
        {"a": txn["account_id"], "t": txn["txn_time"]})]
    history.reverse()
    otp = None
    if txn.get("otp_request_id"):
        otp = jsonable(fetch_one(
            "SELECT id, decision, risk_points, signals_json, verified_device_id FROM otp_requests WHERE id = :id",
            {"id": txn["otp_request_id"]}) or {})
    data = jsonable(txn)
    data["stage_timings"] = _json(txn.get("stage_timings"))
    if otp:
        otp["signals_json"] = _json(otp.get("signals_json"))
    return ok({
        "transaction": data,
        "hits": hits,
        "rules": rules,
        "bands": {"review": review, "block": block},
        "explanation": decision_summary(txn["status"], txn["risk_score"], hits, review, block),
        "alert": jsonable(alert) if alert else None,
        "history": history,
        "otp_request": otp,
    })
