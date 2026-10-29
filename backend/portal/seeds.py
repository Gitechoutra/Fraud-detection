"""
portal/seeds.py
===============
Runs every seeder in dependency order. Idempotent: running it twice adds
nothing the second time. Prints row counts per table at the end.

    flask seed            (or: python -m portal.seeds)
"""

from sqlalchemy import text

from portal.extensions import db
from portal.seeders import (
    seed_admin,
    seed_customers,
    seed_demo_story,
    seed_demo_users,
    seed_merchants,
    seed_roles,
    seed_rules,
    seed_transactions,
    seed_watchlist,
)
from portal.services import simulator

TABLES = [
    "roles", "users", "fraud_rules", "system_settings", "customers", "accounts", "merchants",
    "devices", "sessions", "beneficiaries", "transactions", "rule_hits", "watchlist", "alerts",
    "cases", "case_notes", "otp_requests", "device_approvals", "notifications", "audit_log",
    "metric_runs", "daily_stats", "token_blocklist", "customer_users", "fraudster_users", "stolen_credentials",
    "customer_alerts", "attack_events",
]


def refresh_daily_stats():
    db.session.execute(text(
        """
        INSERT INTO daily_stats (stat_date, total, approved, review, blocked, total_amount,
                                 blocked_amount, avg_decision_ms, refreshed_at)
        SELECT stat_date, total, approved, review, blocked, total_amount, blocked_amount,
               avg_decision_ms, NOW(3)
          FROM v_daily_stats
        ON DUPLICATE KEY UPDATE total = VALUES(total), approved = VALUES(approved),
               review = VALUES(review), blocked = VALUES(blocked), total_amount = VALUES(total_amount),
               blocked_amount = VALUES(blocked_amount), avg_decision_ms = VALUES(avg_decision_ms),
               refreshed_at = VALUES(refreshed_at)
        """
    ))
    db.session.commit()


def row_counts():
    return {t: db.session.execute(text(f"SELECT COUNT(*) FROM `{t}`")).scalar() for t in TABLES}


def run_all(log=print, customers=seed_customers.CUSTOMER_COUNT, history_days=seed_transactions.HISTORY_DAYS,
            frauds_per_rule=5):
    log("Seeding database...")
    seed_roles.run(log)
    seed_admin.run(log)
    seed_rules.run(log)
    seed_merchants.run(log)
    seed_watchlist.run(log)
    seed_customers.run(log, count=customers)
    seed_demo_story.run(log)
    seed_demo_users.run(log)
    seed_transactions.run(log, days=history_days, frauds_per_rule=frauds_per_rule)
    refresh_daily_stats()
    simulator.clear_cache()
    log("Row counts:")
    for table, count in row_counts().items():
        log(f"  {table:<18} {count:>8,}")


if __name__ == "__main__":
    from portal import create_app

    with create_app().app_context():
        run_all()
