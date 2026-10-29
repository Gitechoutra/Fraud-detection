"""
portal/services/master_data.py
==============================
Shares one developer's database contents with the rest of the team through
git and `flask db upgrade`.

    flask export-master-data     snapshot this DB into portal/master_data/
                                 and write a migration that loads it
    flask db upgrade             (teammates) runs that migration -> same data
    flask load-master-data       load the snapshot by hand (--replace to wipe first)

Only the newest snapshot is kept in the repo. Every export writes a new
migration; an older snapshot migration finds the snapshot has moved on and
does nothing, so the data is loaded once, by the newest one.

Not shared: staff passwords, login sessions, revoked tokens and the audit
log. Staff users are shared by name and role only; one missing on the other
side is created with an unusable random password (the default logins then
get theirs from .env at server start; others need a reset on the Users page).
Columns that point at a staff user are stored as the username and matched up
again on load.
"""

import gzip
import json
import os
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import text

from portal.extensions import db

SNAPSHOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "master_data"))
SNAPSHOT_PATH = os.path.join(SNAPSHOT_DIR, "snapshot.json.gz")

# Parents before children.
MASTER_TABLES = [
    "roles", "fraud_rules", "system_settings", "merchants", "watchlist",
    "customers", "accounts", "devices", "beneficiaries",
]
HISTORY_TABLES = [
    "otp_requests", "device_approvals", "notifications", "transactions", "rule_hits",
    "alerts", "cases", "case_notes", "daily_stats", "metric_runs",
]
USER_COLUMNS = {"alerts": ["assigned_to"], "cases": ["analyst_id"], "case_notes": ["author_id"]}
CHUNK = 1000


def _plain(v):
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, datetime):
        return v.isoformat(sep=" ")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, timedelta):
        return str(v)
    if isinstance(v, bytes):
        return v.decode("utf-8")
    return v


def export_snapshot(revision, include_history=True, log=print):
    """Reads the shared tables into SNAPSHOT_PATH. Returns {table: rows}."""
    usernames = dict(db.session.execute(text("SELECT id, username FROM users")).all())
    tables = MASTER_TABLES + (HISTORY_TABLES if include_history else [])
    staff = db.session.execute(text(
        "SELECT u.username, u.full_name, r.name AS role, u.is_active "
        "FROM users u JOIN roles r ON r.id = u.role_id ORDER BY u.id"
    ))
    snapshot = {"revision": revision, "created_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
                "users": [dict(r._mapping) for r in staff], "tables": {}}
    counts = {}
    for table in tables:
        result = db.session.execute(text(f"SELECT * FROM `{table}` ORDER BY 1"))
        columns = list(result.keys())
        user_idx = [columns.index(c) for c in USER_COLUMNS.get(table, [])]
        rows = []
        for r in result:
            row = [_plain(v) for v in r]
            for i in user_idx:
                row[i] = usernames.get(row[i])
            rows.append(row)
        snapshot["tables"][table] = {"columns": columns, "rows": rows}
        counts[table] = len(rows)
        log(f"  {table:<18} {len(rows):>8,} rows")
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    with gzip.open(SNAPSHOT_PATH, "wt", encoding="utf-8") as fh:
        json.dump(snapshot, fh, ensure_ascii=False, separators=(",", ":"))
    log(f"Saved {os.path.relpath(SNAPSHOT_PATH)} ({os.path.getsize(SNAPSHOT_PATH) / 1e6:.1f} MB)")
    return counts


def read_snapshot():
    if not os.path.exists(SNAPSHOT_PATH):
        return None
    with gzip.open(SNAPSHOT_PATH, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def load_snapshot(connection=None, revision=None, replace=False, log=print):
    """Upserts the snapshot rows by primary key. With `revision`, loads only
    if the snapshot on disk was written for that migration. `replace` first
    empties every table in the snapshot.

    `connection` is a SQLAlchemy Connection (Alembic passes its own); default
    is the app's engine.
    """
    snapshot = read_snapshot()
    if snapshot is None:
        log("  master data: no snapshot file, nothing to load")
        return
    if revision is not None and snapshot["revision"] != revision:
        log("  master data: a newer snapshot will be loaded by a later migration")
        return

    own = connection is None
    conn = db.engine.connect() if own else connection
    try:
        conn.execute(text("SET @app_actor = 'master-data'"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        user_ids = None
        tables = snapshot["tables"]
        if replace:
            for table in reversed(list(tables)):
                conn.execute(text(f"DELETE FROM `{table}`"))
        for table, data in tables.items():
            if table in USER_COLUMNS and user_ids is None:
                _ensure_users(conn, snapshot.get("users", []))
                user_ids = dict(conn.execute(text("SELECT username, id FROM users")).all())
            live = {r[0] for r in conn.execute(text(f"SHOW COLUMNS FROM `{table}`"))}
            keep = [i for i, c in enumerate(data["columns"]) if c in live]
            cols = [data["columns"][i] for i in keep]
            user_cols = set(USER_COLUMNS.get(table, []))
            names = [f"p{n}" for n in range(len(cols))]
            sql = text(
                f"INSERT INTO `{table}` ({', '.join(f'`{c}`' for c in cols)}) "
                f"VALUES ({', '.join(':' + n for n in names)}) "
                f"ON DUPLICATE KEY UPDATE {', '.join(f'`{c}` = VALUES(`{c}`)' for c in cols)}"
            )
            params = []
            for row in data["rows"]:
                values = [row[i] for i in keep]
                for k, c in enumerate(cols):
                    if c in user_cols and values[k] is not None:
                        values[k] = user_ids.get(values[k])
                params.append(dict(zip(names, values)))
            for i in range(0, len(params), CHUNK):
                conn.execute(sql, params[i:i + CHUNK])
            log(f"  {table:<18} {len(params):>8,} rows")
        if own:
            conn.commit()
    finally:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        if own:
            conn.close()
    log(f"Master data loaded (snapshot taken {snapshot['created_at']}).")


def _ensure_users(conn, users):
    """Creates staff users missing here, with an unusable random password."""
    from portal.helpers.auth_helpers import hash_password

    existing = {r[0] for r in conn.execute(text("SELECT username FROM users"))}
    for u in users:
        if u["username"] in existing:
            continue
        conn.execute(text(
            "INSERT INTO users (username, full_name, password_hash, role_id, is_active, created_at) "
            "SELECT :username, :full_name, :pw, id, :is_active, NOW() FROM roles WHERE name = :role"
        ), {**u, "pw": hash_password(uuid.uuid4().hex)})


MIGRATION_TEMPLATE = '''"""master data snapshot ({created})

Loads portal/master_data/snapshot.json.gz, written by `flask export-master-data`.

Revision ID: {revision}
Revises: {down}
"""

from alembic import op

from portal.services.master_data import load_snapshot

revision = "{revision}"
down_revision = "{down}"
branch_labels = None
depends_on = None


def upgrade():
    load_snapshot(op.get_bind(), revision=revision)


def downgrade():
    pass
'''


def new_revision():
    return uuid.uuid4().hex[:12]


def write_migration(config, revision, log=print):
    """Creates the snapshot migration after the current head."""
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(config)
    down = script.get_current_head()
    created = datetime.now().strftime("%Y-%m-%d %H:%M")
    path = os.path.join(script.versions, f"{revision}_master_data_snapshot.py")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(MIGRATION_TEMPLATE.format(revision=revision, down=down, created=created))
    log(f"Wrote migration {os.path.relpath(path)}")
