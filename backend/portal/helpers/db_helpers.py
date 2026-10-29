"""
portal/helpers/db_helpers.py
============================
Calling stored procedures, running parameterised SQL, creating the databases
and loading the portal/sql/*.sql objects.

All SQL here takes parameters -- values are never formatted into the string.
"""

import os
import re
from datetime import date, datetime
from decimal import Decimal

import pymysql
from sqlalchemy import text

from portal.extensions import db

SQL_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "sql"))

# MySQL error codes that are safe to ignore when re-running the SQL files.
DUPLICATE_KEY_NAME = 1061


def call_procedure(name, args=()):
    """CALL a stored procedure on the *current session's* connection, so it
    runs inside the same database transaction as whatever the caller did
    before (e.g. the INSERT of the transaction being evaluated).

    Returns the procedure's final SELECT as a list of dicts.
    """
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError(f"Invalid procedure name: {name!r}")
    dbapi_conn = db.session.connection().connection.dbapi_connection
    cursor = dbapi_conn.cursor()
    try:
        placeholders = ", ".join(["%s"] * len(args))
        cursor.execute(f"CALL {name}({placeholders})", tuple(args))
        rows = []
        if cursor.description:
            cols = [c[0] for c in cursor.description]
            rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
        # Drain the trailing status result set a CALL always produces, or
        # the next statement on this connection fails "out of sync".
        while cursor.nextset():
            pass
        return rows
    finally:
        cursor.close()


def jsonable(row):
    """Row dict -> JSON-friendly dict (Decimal -> float, datetime -> ISO)."""
    out = {}
    for k, v in row.items():
        if isinstance(v, Decimal):
            out[k] = float(v)
        elif isinstance(v, (datetime, date)):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def fetch_all(sql, params=None):
    result = db.session.execute(text(sql), params or {})
    return [dict(r._mapping) for r in result]


def fetch_one(sql, params=None):
    result = db.session.execute(text(sql), params or {}).first()
    return dict(result._mapping) if result else None


def scalar(sql, params=None):
    return db.session.execute(text(sql), params or {}).scalar()


def execute(sql, params=None):
    return db.session.execute(text(sql), params or {})


def set_actor(username):
    """Tells the audit triggers who is making the change on this connection."""
    db.session.execute(text("SET @app_actor = :u"), {"u": username})


# --------------------------------------------------------------------------
# Database creation
# --------------------------------------------------------------------------


def create_databases(names, host, port, user, password):
    """CREATE DATABASE IF NOT EXISTS for each name, through the Python driver
    so it works even when the `mysql` client is not on PATH."""
    conn = pymysql.connect(host=host, port=int(port), user=user, password=password, charset="utf8mb4")
    try:
        with conn.cursor() as cur:
            for name in names:
                if not re.fullmatch(r"[A-Za-z0-9_]+", name):
                    raise ValueError(f"Invalid database name: {name!r}")
                cur.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{name}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------
# SQL object loader (indexes, views, triggers, procedures)
# --------------------------------------------------------------------------


def split_sql_script(script):
    """Splits a MySQL script into statements, honouring DELIMITER lines.

    The driver doesn't understand the client-side `DELIMITER $$` directive,
    so we interpret it here: a DELIMITER line switches the current statement
    terminator, and is itself dropped. Files therefore stay valid scripts that
    also run unchanged in MySQL Workbench.
    """
    delimiter = ";"
    statements, buf = [], []
    for line in script.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("DELIMITER "):
            delimiter = stripped.split(None, 1)[1]
            continue
        if not buf and (not stripped or stripped.startswith("--")):
            continue
        buf.append(line)
        if stripped.endswith(delimiter):
            stmt = "\n".join(buf).rstrip()
            stmt = stmt[: -len(delimiter)].strip()
            if stmt:
                statements.append(stmt)
            buf = []
    tail = "\n".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def sql_files():
    return sorted(f for f in os.listdir(SQL_DIR) if f.endswith(".sql"))


def load_sql_objects_if_head(connection, revision, log=print):
    """For migrations: the SQL files always describe the *latest* schema, so
    only the newest migration may load them all (an older one, replayed on a
    fresh database, would reference columns that do not exist yet). Returns
    True if this revision is the head and the files were loaded."""
    from alembic import context
    from alembic.script import ScriptDirectory

    if revision not in ScriptDirectory.from_config(context.config).get_heads():
        log("  SQL objects: loaded by a later migration")
        return False
    load_sql_objects(connection, log=log)
    return True


def load_sql_objects(connection=None, log=print, files=None):
    """Executes every portal/sql/*.sql file in name order (or just `files`).
    Safe to re-run: views use CREATE OR REPLACE, triggers/procedures are
    dropped first, and an index that already exists is skipped.

    `connection` is a SQLAlchemy Connection (Alembic passes its own); default
    is the app's engine.
    """
    own = connection is None
    conn = db.engine.connect() if own else connection
    try:
        dbapi = conn.connection.dbapi_connection
        for fname in files or sql_files():
            with open(os.path.join(SQL_DIR, fname), encoding="utf-8") as fh:
                statements = split_sql_script(fh.read())
            done = skipped = 0
            cur = dbapi.cursor()
            try:
                for stmt in statements:
                    try:
                        cur.execute(stmt)
                        while cur.nextset():
                            pass
                        done += 1
                    except pymysql.err.OperationalError as exc:
                        if exc.args[0] == DUPLICATE_KEY_NAME:
                            skipped += 1
                            continue
                        raise
            finally:
                cur.close()
            log(f"  {fname}: {done} statements executed, {skipped} already present")
        if own:
            conn.commit()
    finally:
        if own:
            conn.close()
