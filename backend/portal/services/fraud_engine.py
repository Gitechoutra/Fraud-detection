"""
portal/services/fraud_engine.py
===============================
ingest -> persist -> CALL sp_evaluate_transaction -> commit.

Python only orchestrates. The nine rules, the score and the decision all
live in MySQL (portal/sql/04_sp_evaluate_transaction.sql). This module:

  1. resolves the account (by id or number) and checks the payee belongs to it,
  2. INSERTs the payment as PENDING and CALLs the procedure on the same
     connection, inside the same database transaction,
  3. records the decision time, tells the customer if it was held/blocked,
     and commits ONCE. Any error rolls everything back, so a payment never
     exists without its decision and evidence.

Idempotency: `external_ref` is UNIQUE. A repeated reference fails the INSERT,
the work is rolled back, and the stored decision is returned instead -- so a
retried request never creates a second payment (and the common case, a new
payment, costs no extra lookup).

The path is kept lean on purpose: one INSERT, one CALL (which also returns
the rule hits as JSON), one UPDATE, one COMMIT.
"""

import json
import logging
from datetime import datetime

from pymysql.err import IntegrityError as PyMySQLIntegrityError
from pymysql.err import OperationalError as PyMySQLOperationalError
from sqlalchemy.exc import IntegrityError, OperationalError

from portal.extensions import db
from portal.helpers.db_helpers import call_procedure, fetch_all, fetch_one, scalar
from portal.helpers.explain import inr
from portal.helpers.responses import AppError
from portal.helpers.timing import now_ms
from portal.models import Transaction
from portal.services.notifier import get_notifier

DEADLOCK = 1213
LOCK_WAIT_TIMEOUT = 1205
DUPLICATE_ENTRY = 1062
FOREIGN_KEY_MISSING = 1452
MAX_ATTEMPTS = 3

# Sources that are bulk/offline and must not message customers.
SILENT_SOURCES = {"SEED", "EVALUATION"}

# One line per decision with its latency, written to logs/app.log only
# (printing every payment to a Windows console would slow the engine down).
decision_log = logging.getLogger("portal.decisions")

_txn_table = Transaction.__table__


def _mysql_code(exc):
    orig = getattr(exc, "orig", exc)
    return orig.args[0] if getattr(orig, "args", None) else None


def _account_id(payload):
    if payload.get("account_id"):
        return payload["account_id"]
    account_id = scalar("SELECT id FROM accounts WHERE account_no = :no", {"no": payload["account_no"]})
    if account_id is None:
        raise AppError("That account does not exist.", "ACCOUNT_NOT_FOUND", 404)
    return account_id


def _check_payee(beneficiary_id, account_id):
    owner = scalar("SELECT account_id FROM beneficiaries WHERE id = :id", {"id": beneficiary_id})
    if owner != account_id:
        raise AppError("That payee does not belong to this account.", "PAYEE_NOT_FOUND", 404)


def existing_decision(external_ref):
    txn = Transaction.query.filter_by(external_ref=external_ref).first()
    return decision_payload(txn, duplicate=True) if txn else None


def decision_payload(txn, duplicate=False):
    """The decision of a stored payment (used for duplicates and status pages)."""
    hits = fetch_all(
        "SELECT rule_code, weight_applied, observed_value, detail_text "
        "FROM rule_hits WHERE txn_id = :id ORDER BY rule_code",
        {"id": txn.id},
    )
    alert_id = None
    if txn.status in ("REVIEW", "BLOCKED"):
        alert_id = scalar("SELECT id FROM alerts WHERE txn_id = :id", {"id": txn.id})
    return {
        "txn_id": txn.id,
        "external_ref": txn.external_ref,
        "account_id": txn.account_id,
        "amount": float(txn.amount),
        "status": txn.status,
        "risk_score": txn.risk_score,
        "decision_ms": float(txn.decision_ms) if txn.decision_ms is not None else None,
        "total_ms": None,
        "stage_timings": txn.stage_timings,
        "rules": hits,
        "alert_id": alert_id,
        "duplicate": duplicate,
    }


def _notify_customer(account_id, txn_id, amount, status):
    """'Was this you?' message for anything held or blocked."""
    acc = fetch_one("SELECT customer_id, account_no FROM accounts WHERE id = :id", {"id": account_id})
    verb = "stopped" if status == "BLOCKED" else "paused"
    get_notifier().send(
        acc["customer_id"],
        "SMS",
        "Was this you?",
        f"FraudShield {verb} a payment of {inr(amount)} from your account "
        f"ending {acc['account_no'][-4:]}. If this was you, reply YES. If not, reply NO "
        "and call your bank. The bank never asks for your OTP.",
        kind="ALERT",
        ref_id=txn_id,
    )


def _ingest_once(payload, source, t_received):
    timings = {}
    account_id = _account_id(payload)
    if payload.get("beneficiary_id"):
        _check_payee(payload["beneficiary_id"], account_id)
    row = {
        "external_ref": payload["external_ref"],
        "account_id": account_id,
        "merchant_id": payload.get("merchant_id"),
        "beneficiary_id": payload.get("beneficiary_id"),
        "otp_request_id": payload.get("otp_request_id"),
        "amount": payload["amount"],
        "currency": payload.get("currency") or "INR",
        "channel": payload["channel"],
        "city": payload.get("city"),
        "device_id": payload.get("device_id"),
        "ip_address": payload.get("ip_address"),
        "txn_time": payload.get("txn_time") or datetime.now(),
        "risk_score": 0,
        "status": "PENDING",
        "is_fraud_label": payload.get("is_fraud_label"),
        "scenario": payload.get("scenario"),
        "source": payload.get("source") or source,
        "created_at": datetime.now(),
    }
    timings["ingest"] = round(now_ms() - t_received, 3)

    t_save = now_ms()
    txn_id = db.session.execute(_txn_table.insert().values(**row)).inserted_primary_key[0]
    timings["save"] = round(now_ms() - t_save, 3)

    result = call_procedure("sp_evaluate_transaction", (txn_id,))[0]
    for key in ("rules", "score", "decide", "alert"):
        timings[key] = float(result[f"{key}_ms"] or 0)
    hits = sorted(json.loads(result["hits_json"]) if result["hits_json"] else [], key=lambda h: h["rule_code"])

    decision_ms = round(now_ms() - t_received, 2)
    db.session.execute(
        _txn_table.update().where(_txn_table.c.id == txn_id).values(decision_ms=decision_ms, stage_timings=timings)
    )
    status = result["status"]
    if status != "APPROVED" and row["source"] not in SILENT_SOURCES:
        _notify_customer(account_id, txn_id, row["amount"], status)
    db.session.commit()

    decision = {
        "txn_id": txn_id,
        "external_ref": row["external_ref"],
        "account_id": account_id,
        "amount": float(row["amount"]),
        "status": status,
        "risk_score": int(result["risk_score"]),
        "decision_ms": decision_ms,
        "total_ms": round(now_ms() - t_received, 2),
        "stage_timings": timings,
        "rules": hits,
        "alert_id": result["alert_id"],
        "duplicate": False,
    }
    decision_log.info(
        "txn %s (%s) -> %s score=%s rules=%s decided in %.1f ms",
        txn_id, row["external_ref"], status, decision["risk_score"],
        ",".join(h["rule_code"] for h in hits) or "-", decision_ms,
    )
    return decision


def ingest(payload, source="API", t_received=None):
    """Evaluates one payment and returns its decision (see decision_payload).

    `payload` is a validated TransactionSchema dict. `t_received` (ms from
    helpers.timing.now_ms) lets the API include request parsing in the
    measured decision time.
    """
    t_received = t_received if t_received is not None else now_ms()
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return _ingest_once(payload, source, t_received)
        except (IntegrityError, PyMySQLIntegrityError) as exc:
            db.session.rollback()
            code = _mysql_code(exc)
            if code == DUPLICATE_ENTRY:
                existing = existing_decision(payload["external_ref"])
                if existing:
                    return existing
            if code == FOREIGN_KEY_MISSING:
                raise AppError("That account, merchant or payee does not exist.", "REFERENCE_NOT_FOUND", 404)
            raise
        except (OperationalError, PyMySQLOperationalError) as exc:
            db.session.rollback()
            if _mysql_code(exc) in (DEADLOCK, LOCK_WAIT_TIMEOUT) and attempt < MAX_ATTEMPTS:
                decision_log.warning(
                    "Deadlock on %s, retrying (%s/%s)", payload["external_ref"], attempt, MAX_ATTEMPTS
                )
                continue
            raise
        except Exception:
            db.session.rollback()
            raise
    raise AppError("Could not save the payment. Please retry.", "RETRY_LATER", 503)
