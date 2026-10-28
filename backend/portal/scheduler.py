"""
portal/scheduler.py
===================
Background jobs (APScheduler):

  every 1 minute   expire stale OTPs and device approvals
  every 5 minutes  refresh daily_stats from v_daily_stats
  nightly 02:00    mark dormant accounts, delete notifications older than 30 days

`init_scheduler(app)` is called by app.py / wsgi.py only. Under the Flask
debug reloader the code runs in two processes; the scheduler starts only in
the child that actually serves requests (WERKZEUG_RUN_MAIN=true), so jobs
are never scheduled twice.
"""

import os

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import text

from portal.extensions import db

_scheduler = None


def _job(app, fn):
    def run():
        with app.app_context():
            try:
                result = fn()
                if result:
                    app.logger.info("Scheduler %s: %s", fn.__name__, result)
            except Exception:
                db.session.rollback()
                app.logger.exception("Scheduler job %s failed", fn.__name__)
            finally:
                db.session.remove()

    return run


def expire_stale_otps():
    from portal.services.otp_shield import expire_stale

    result = expire_stale()
    return result if any(result.values()) else None


def refresh_daily_stats():
    from portal.seeds import refresh_daily_stats as refresh

    refresh()


def nightly_maintenance():
    dormant = db.session.execute(text(
        "UPDATE accounts SET status = 'DORMANT' "
        "WHERE status = 'ACTIVE' AND COALESCE(last_txn_at, opened_on) < NOW() - INTERVAL "
        "(SELECT CAST(param_1 AS UNSIGNED) FROM fraud_rules WHERE rule_code = 'R8') DAY"
    )).rowcount
    old = db.session.execute(text(
        "DELETE FROM notifications WHERE created_at < NOW() - INTERVAL 30 DAY"
    )).rowcount
    db.session.commit()
    return {"accounts_marked_dormant": dormant, "notifications_deleted": old}


def init_scheduler(app, reloader=False):
    """reloader=True when running under the Flask debug reloader (app.py)."""
    global _scheduler
    if not app.config.get("SCHEDULER_ENABLED") or _scheduler is not None:
        return None
    if reloader and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return None  # reloader parent process: the child will start it
    _scheduler = BackgroundScheduler(daemon=True, timezone=None)
    _scheduler.add_job(_job(app, expire_stale_otps), "interval", minutes=1, id="expire_otps")
    _scheduler.add_job(_job(app, refresh_daily_stats), "interval", minutes=5, id="daily_stats")
    _scheduler.add_job(_job(app, nightly_maintenance), "cron", hour=2, minute=0, id="nightly")
    _scheduler.start()
    app.logger.info("Scheduler started with %s jobs", len(_scheduler.get_jobs()))
    return _scheduler
