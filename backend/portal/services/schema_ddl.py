"""
portal/services/schema_ddl.py
=============================
The CREATE TABLE script for the whole schema (backend/docs/schema.sql),
generated from the SQLAlchemy models so it always matches them.

`flask export-ddl` rewrites the file; tests/test_spec_requirements.py fails
if it is out of date. Run the script in an empty MySQL 8 database, then the
portal/sql/*.sql files (indexes, views, triggers, procedures) -- which is
what `flask db upgrade` does in one step.
"""

import os

from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateIndex, CreateTable

from portal.extensions import db

DDL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "docs", "schema.sql"))
TABLE_OPTIONS = " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"

HEADER = """-- ===========================================================================
-- schema.sql  --  FraudShield tables (MySQL 8, InnoDB)
-- ---------------------------------------------------------------------------
-- Generated from the SQLAlchemy models by `flask export-ddl`; do not edit by
-- hand. Run it in an empty database, then portal/sql/01..06_*.sql for the
-- indexes, views, triggers and stored procedures (the fraud engine).
-- `flask db upgrade` does all of this, plus the shared master data.
-- ===========================================================================
"""


def render():
    import portal.models  # noqa: F401  (registers every table)

    dialect = mysql.dialect()
    parts = [HEADER]
    for table in db.metadata.sorted_tables:
        create = str(CreateTable(table).compile(dialect=dialect)).strip()
        parts.append(f"\n-- {table.name}\n{create}{TABLE_OPTIONS};\n")
        for index in sorted(table.indexes, key=lambda i: i.name):
            parts.append(str(CreateIndex(index).compile(dialect=dialect)).strip() + ";\n")
    return "".join(parts)


def export(path=DDL_PATH):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render())
    return path
