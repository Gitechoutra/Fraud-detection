"""master data snapshot (2026-10-28 19:14)

Loads portal/master_data/snapshot.json.gz, written by `flask export-master-data`.

Revision ID: c7322963b6d3
Revises: b7c1d2e3f4a5
"""

from alembic import op

from portal.services.master_data import load_snapshot

revision = "c7322963b6d3"
down_revision = "b7c1d2e3f4a5"
branch_labels = None
depends_on = None


def upgrade():
    load_snapshot(op.get_bind(), revision=revision)


def downgrade():
    pass
