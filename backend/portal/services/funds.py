"""
portal/services/funds.py
========================
What happens to the money once the fraud engine has decided.

    APPROVED -> debited from the balance                    funds_status DEBITED
    REVIEW   -> reserved: held_amount += amount (not paid)   funds_status HELD
    BLOCKED  -> nothing moves                                funds_status NOT_MOVED

and later, for a held payment:

    customer confirms "This was me" -> hold released, payment completed once
                                                             funds_status PAID_AFTER_REVIEW
    customer reports "Not me"       -> hold released, nothing paid
                                                             funds_status RELEASED

Every change is one conditional UPDATE that also checks the current state
(e.g. "... WHERE funds_status = 'HELD'"), so a repeated or concurrent
request finds nothing to do instead of paying twice; the account row is
locked by the same UPDATE. CHECK constraints on accounts (balance >= 0,
0 <= held_amount <= balance) are the last line of defence.

settle_decision() runs inside fraud_engine's database transaction, before its
single COMMIT: if the money cannot move (not enough available balance), the
whole payment is rolled back and refused, so a payment never exists with an
inconsistent balance.
"""

from portal.helpers.db_helpers import execute, fetch_one
from portal.helpers.responses import AppError

# Synthetic traffic only exercises the rules and moves no money: seeded
# history, evaluation data sets and the Fraud Lab / live stream (which picks
# random demo accounts). Everything else -- the API, the customer app, the
# demo bank and the fraudster console -- moves real (demo) money.
NO_MONEY_SOURCES = {"SEED", "EVALUATION", "SIMULATOR"}


def _insufficient():
    return AppError("Not enough available balance for this payment.", "INSUFFICIENT_FUNDS", 422)


def settle_decision(account_id, txn_id, amount, status, source):
    """Moves (or reserves) the money for a just-decided payment."""
    if source in NO_MONEY_SOURCES:
        return None
    if status == "APPROVED":
        moved = execute(
            "UPDATE accounts SET balance = balance - :amt "
            "WHERE id = :id AND balance - held_amount >= :amt", {"amt": amount, "id": account_id}).rowcount
        if not moved:
            raise _insufficient()
        funds = "DEBITED"
    elif status == "REVIEW":
        moved = execute(
            "UPDATE accounts SET held_amount = held_amount + :amt "
            "WHERE id = :id AND balance - held_amount >= :amt", {"amt": amount, "id": account_id}).rowcount
        if not moved:
            raise _insufficient()
        funds = "HELD"
    else:
        funds = "NOT_MOVED"
    execute("UPDATE transactions SET funds_status = :f WHERE id = :id", {"f": funds, "id": txn_id})
    return funds


def _held_txn(txn_id):
    return fetch_one("SELECT account_id, amount FROM transactions WHERE id = :id AND funds_status = 'HELD' FOR UPDATE",
                     {"id": txn_id})


def complete_held(txn_id):
    """Customer confirmed a held payment: pay it exactly once. Returns True
    if this call paid it, False if it was not (or no longer) held."""
    txn = _held_txn(txn_id)
    if txn is None:
        return False
    if not execute("UPDATE transactions SET funds_status = 'PAID_AFTER_REVIEW' WHERE id = :id AND funds_status = 'HELD'",
                   {"id": txn_id}).rowcount:
        return False
    moved = execute(
        "UPDATE accounts SET held_amount = held_amount - :amt, balance = balance - :amt "
        "WHERE id = :a AND held_amount >= :amt AND balance >= :amt", {"amt": txn["amount"], "a": txn["account_id"]},
    ).rowcount
    if not moved:
        raise AppError("The held money no longer matches this payment. Please contact the bank.", "FUNDS_MISMATCH", 409)
    return True


def release_held(txn_id):
    """Payment reported as fraud: give the reserved money back, pay nothing.
    Returns True if this call released it."""
    txn = _held_txn(txn_id)
    if txn is None:
        return False
    if not execute("UPDATE transactions SET funds_status = 'RELEASED' WHERE id = :id AND funds_status = 'HELD'",
                   {"id": txn_id}).rowcount:
        return False
    moved = execute("UPDATE accounts SET held_amount = held_amount - :amt WHERE id = :a AND held_amount >= :amt",
                    {"amt": txn["amount"], "a": txn["account_id"]}).rowcount
    if not moved:
        raise AppError("The held money no longer matches this payment. Please contact the bank.", "FUNDS_MISMATCH", 409)
    return True
