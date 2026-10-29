"""load SQL objects: indexes, views, triggers, stored procedures

Runs every portal/sql/*.sql file (the same loader as `flask init-db-objects`),
so a plain `flask db upgrade` builds the complete fraud engine.

Revision ID: b7c1d2e3f4a5
Revises: ae58f92b1200
"""

from alembic import op

from portal.helpers.db_helpers import load_sql_objects_if_head

revision = "b7c1d2e3f4a5"
down_revision = "ae58f92b1200"
branch_labels = None
depends_on = None


def upgrade():
    # The files describe the latest schema; the newest migration loads them.
    load_sql_objects_if_head(op.get_bind(), revision)


def downgrade():
    for stmt in (
        "DROP PROCEDURE IF EXISTS sp_otp_risk_check",
        "DROP PROCEDURE IF EXISTS sp_evaluate_transaction",
        "DROP FUNCTION IF EXISTS fn_inr",
        "DROP TRIGGER IF EXISTS trg_fraud_rules_audit_update",
        "DROP TRIGGER IF EXISTS trg_watchlist_audit_insert",
        "DROP TRIGGER IF EXISTS trg_watchlist_audit_delete",
        "DROP TRIGGER IF EXISTS trg_cases_audit_update",
        "DROP VIEW IF EXISTS v_alert_queue",
        "DROP VIEW IF EXISTS v_rule_precision",
        "DROP VIEW IF EXISTS v_daily_stats",
    ):
        op.execute(stmt)
