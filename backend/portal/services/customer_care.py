"""
portal/services/customer_care.py
================================
Fraud alerts in the customer's banking app, and the customer's answer.

create_decision_alert()  called by fraud_engine for every held (WARNING) or
                         blocked (DANGER) payment, inside the same database
                         transaction as the decision. The one-sentence reason
                         is the fired rule's own plain-English explanation
                         from fraud_rules -- no fraud logic lives here.
confirm()                "This was me": password checked again, current
                         device trusted, held money paid exactly once.
report_not_me()          "Not me": held money released (nothing paid), the
                         fraudster's session ended, device / IP / payee put on
                         the watchlist, staff case marked.

Everything is derived from the stored transaction (owner, device, IP, payee,
fraudster), never from what the client sends.
"""

from datetime import datetime

from portal.extensions import db
from portal.helpers.auth_helpers import check_password
from portal.helpers.db_helpers import execute, fetch_all, fetch_one, scalar, set_actor
from portal.helpers.explain import inr
from portal.helpers.responses import AppError
from portal.models import CustomerAlert, CustomerUser
from portal.services import fraud_engine, funds

REPORT_ACTOR = "customer-report"


def _reason(txn_id):
    """The strongest fired rule's plain-English explanation (one sentence)."""
    row = fetch_one(
        "SELECT r.simple_explanation FROM rule_hits rh JOIN fraud_rules r ON r.rule_code = rh.rule_code "
        "WHERE rh.txn_id = :id ORDER BY rh.weight_applied DESC, rh.rule_code LIMIT 1", {"id": txn_id})
    return row["simple_explanation"] if row else "This payment did not look like your usual activity."


def create_decision_alert(txn_id, account_id, amount, status, payee_label=None):
    customer_id = scalar("SELECT customer_id FROM accounts WHERE id = :id", {"id": account_id})
    to = f" to {payee_label}" if payee_label else ""
    if status == "BLOCKED":
        severity, title = "DANGER", f"Blocked: {inr(amount)}{to}"
    else:
        severity, title = "WARNING", f"On hold: {inr(amount)}{to} — was this you?"
    execute(
        "INSERT IGNORE INTO customer_alerts (customer_id, txn_id, severity, title, body, action_status, created_at) "
        "VALUES (:c, :t, :s, :title, :body, 'PENDING', NOW(3))",
        {"c": customer_id, "t": txn_id, "s": severity, "title": title[:160], "body": _reason(txn_id)[:500]},
    )


def alerts_for(customer_id, since_id=0, limit=50):
    rows = fetch_all(
        """
        SELECT ca.*, t.external_ref, t.amount, t.status AS txn_status, t.funds_status, t.txn_time,
               (SELECT GROUP_CONCAT(rh.rule_code ORDER BY rh.rule_code) FROM rule_hits rh WHERE rh.txn_id = t.id) AS rules
          FROM customer_alerts ca
          LEFT JOIN transactions t ON t.id = ca.txn_id
         WHERE ca.customer_id = :c AND ca.id > :since
         ORDER BY ca.id DESC LIMIT :lim
        """, {"c": customer_id, "since": since_id, "lim": limit})
    return rows


def _owned_alert(customer_id, alert_id):
    """The alert and its payment, only if it belongs to this customer. Locks
    the alert row so two answers to the same alert are processed one at a time."""
    row = fetch_one(
        """
        SELECT ca.id, ca.txn_id, ca.severity, ca.action_status, t.account_id, t.status, t.funds_status,
               t.device_id, t.ip_address, t.beneficiary_id, t.amount
          FROM customer_alerts ca JOIN transactions t ON t.id = ca.txn_id
         WHERE ca.id = :id AND ca.customer_id = :c
           FOR UPDATE OF ca
        """, {"id": alert_id, "c": customer_id})
    if row is None:
        raise AppError("We couldn't find that alert.", "NOT_FOUND", 404)
    if row["severity"] == "INFO":
        raise AppError("This message needs no answer.", "NOTHING_TO_ANSWER", 409)
    if row["action_status"] != "PENDING":
        raise AppError("You have already answered this alert.", "ALREADY_ANSWERED", 409)
    return row


def _mark(alert_id, status):
    # Conditional: a replayed request finds the alert no longer PENDING.
    if not execute("UPDATE customer_alerts SET action_status = :s, responded_at = NOW(3), read_at = COALESCE(read_at, NOW(3)) "
                   "WHERE id = :id AND action_status = 'PENDING'", {"s": status, "id": alert_id}).rowcount:
        raise AppError("You have already answered this alert.", "ALREADY_ANSWERED", 409)


def _mark_case(txn_id, response, actor):
    set_actor(actor)
    execute("UPDATE cases ca JOIN alerts al ON al.id = ca.alert_id SET ca.customer_response = :r "
            "WHERE al.txn_id = :t", {"r": response, "t": txn_id})


def confirm(customer_user_id, customer_id, alert_id, password, device_id):
    cu = db.session.get(CustomerUser, customer_user_id)
    if cu is None or not check_password(password, cu.password_hash):
        raise AppError("That password is not right.", "INVALID_CREDENTIALS", 401)
    try:
        row = _owned_alert(customer_id, alert_id)
        status = scalar("SELECT status FROM accounts WHERE id = :id", {"id": row["account_id"]})
        if status == "FROZEN":
            raise AppError("This account is frozen. Please call the bank.", "ACCOUNT_FROZEN", 423)
        _mark(alert_id, "CONFIRMED_ME")
        # The customer proved who they are on this device: trust it.
        execute(
            "INSERT INTO devices (account_id, device_id, device_label, first_seen, last_seen, is_trusted) "
            "VALUES (:a, :d, 'Confirmed in the banking app', NOW(3), NOW(3), 1) "
            "ON DUPLICATE KEY UPDATE is_trusted = 1, last_seen = NOW(3)", {"a": row["account_id"], "d": device_id})
        paid = funds.complete_held(row["txn_id"]) if row["funds_status"] == "HELD" else False
        fraud_engine.r9_release(row["txn_id"])  # lifts R9 holds and watchlist entries for a genuine payment
        _mark_case(row["txn_id"], "CONFIRMED_ME", f"customer:{cu.username}")
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    finally:
        set_actor(None)
    message = (f"Thanks. {inr(row['amount'])} has been paid." if paid else
               "Thanks. Blocked payments are never sent — you can make the payment again now; this device is trusted.")
    return {"alert_id": alert_id, "action_status": "CONFIRMED_ME", "paid": paid, "message": message}


def report_not_me(customer_user_id, customer_id, alert_id):
    cu = db.session.get(CustomerUser, customer_user_id)
    try:
        row = _owned_alert(customer_id, alert_id)
        _mark(alert_id, "REPORTED_NOT_ME")
        released = funds.release_held(row["txn_id"]) if row["funds_status"] == "HELD" else False

        # End the fraudster's sessions -- the link comes from our own record
        # of the simulated attack, never from the request.
        fraudster_id = scalar("SELECT fraudster_id FROM attack_events WHERE txn_id = :t", {"t": row["txn_id"]})
        if fraudster_id:
            execute("UPDATE fraudster_users SET tokens_valid_after = NOW(3) WHERE id = :id", {"id": fraudster_id})

        # Watchlist what the fraudster used (never the customer's own trusted device).
        trusted = row["device_id"] and scalar(
            "SELECT 1 FROM devices WHERE account_id = :a AND device_id = :d AND is_trusted = 1",
            {"a": row["account_id"], "d": row["device_id"]})
        entries = []
        if not trusted:
            entries += [("DEVICE", row["device_id"]), ("IP", row["ip_address"])]
        if row["beneficiary_id"]:
            entries.append(("ACCOUNT", scalar("SELECT payee_account_no FROM beneficiaries WHERE id = :id",
                                              {"id": row["beneficiary_id"]})))
        set_actor(f"customer:{cu.username if cu else customer_id}")
        watchlisted = []
        for entry_type, value in entries:
            if value and execute(
                "INSERT IGNORE INTO watchlist (entry_type, entry_value, reason, added_by, added_at) "
                "VALUES (:t, :v, :r, :by, NOW(3))",
                {"t": entry_type, "v": value, "r": f"Customer reported payment #{row['txn_id']} as fraud",
                 "by": REPORT_ACTOR},
            ).rowcount:
                watchlisted.append({"entry_type": entry_type, "entry_value": value})
        _mark_case(row["txn_id"], "REPORTED_NOT_ME", f"customer:{cu.username if cu else customer_id}")
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    finally:
        set_actor(None)
    return {
        "alert_id": alert_id,
        "action_status": "REPORTED_NOT_ME",
        "released": released,
        "fraudster_logged_out": bool(fraudster_id),
        "watchlisted": watchlisted,
        "message": ("Reported. The held money is back in your balance and nothing was paid. "
                    if released else "Reported. No money left your account. ") +
                   "The device and payee used have been blocked, and the bank has been told.",
        "reported_at": datetime.now().isoformat(),
    }
