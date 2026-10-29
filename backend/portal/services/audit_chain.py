"""
portal/services/audit_chain.py
==============================
Proves the audit log was not tampered with.

Each audit_log row carries prev_hash and row_hash, written by the
trg_audit_log_chain trigger (portal/sql/03_triggers.sql). verify() re-computes
every hash with the same SQL function, fn_audit_hash, and checks that:

  1. each row's row_hash still matches its content (nothing was edited),
  2. each row's prev_hash is the row_hash of the row before it (nothing was
     removed or inserted in the middle), and
  3. the newest row_hash equals audit_chain.last_hash (nothing was removed
     from the end).
"""

from sqlalchemy import text

from portal.extensions import db
from portal.helpers.db_helpers import fetch_all, scalar

_CHECK = """
    SELECT id, prev_hash, row_hash,
           LAG(row_hash) OVER (ORDER BY id) AS chain_prev,
           fn_audit_hash(prev_hash, actor, action, entity, entity_id,
                         old_value, new_value, logged_at) AS recomputed
      FROM audit_log
     ORDER BY id
"""


def verify():
    rows = fetch_all(_CHECK)
    bad_id, problem = None, None
    for r in rows:
        if r["row_hash"] is None:
            problem = "has no hash (it was never sealed)"
        elif r["recomputed"] != r["row_hash"]:
            problem = "was changed after it was written"
        elif r["prev_hash"] != r["chain_prev"]:
            problem = "does not follow the entry before it (an entry was removed or inserted)"
        if problem:
            bad_id, problem = r["id"], f"Audit entry #{r['id']} {problem}."
            break
    head = scalar("SELECT last_hash FROM audit_chain WHERE id = 1")
    newest = rows[-1]["row_hash"] if rows else None
    if problem is None and head != newest:
        problem = "The newest audit entries were removed from the end of the log."
    return {
        "intact": problem is None,
        "rows": len(rows),
        "head_hash": head,
        "first_bad_id": bad_id,
        "problem": problem,
    }


def seal_existing(connection=None):
    """Gives rows written before the chain existed their hashes, oldest
    first, and records the chain head. Each row can be sealed only once (the
    no-update trigger allows it only while row_hash is NULL)."""
    conn = connection or db.session
    prev = conn.execute(text("SELECT row_hash FROM audit_log WHERE row_hash IS NOT NULL ORDER BY id DESC LIMIT 1")).scalar()
    ids = [r[0] for r in conn.execute(text("SELECT id FROM audit_log WHERE row_hash IS NULL ORDER BY id"))]
    for row_id in ids:
        h = conn.execute(
            text("SELECT fn_audit_hash(:p, actor, action, entity, entity_id, old_value, new_value, logged_at) "
                 "FROM audit_log WHERE id = :id"),
            {"p": prev, "id": row_id},
        ).scalar()
        conn.execute(text("UPDATE audit_log SET prev_hash = :p, row_hash = :h WHERE id = :id"),
                     {"p": prev, "h": h, "id": row_id})
        prev = h
    conn.execute(
        text("INSERT INTO audit_chain (id, last_hash) VALUES (1, :h) ON DUPLICATE KEY UPDATE last_hash = :h"),
        {"h": prev},
    )
    return len(ids)
