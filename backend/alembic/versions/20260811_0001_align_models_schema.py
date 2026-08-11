"""align existing databases with the current ORM models

Revision ID: 20260811_0001
Revises: 20260706_0002
Create Date: 2026-08-11
"""
from alembic import op
import sqlalchemy as sa

from backend.app.migrations import ALL_TABLE_NAMES, align_columns, align_indexes, ensure_tables

revision = "20260811_0001"
down_revision = "20260706_0002"
branch_labels = None
depends_on = None

_ADDED_COLUMNS: list[tuple[str, str]] = []


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    missing_tables = [n for n in ALL_TABLE_NAMES if not inspector.has_table(n)]
    ensure_tables(bind, missing_tables)
    align_columns(bind, ALL_TABLE_NAMES, _ADDED_COLUMNS)
    align_indexes(bind, ALL_TABLE_NAMES)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table_name, column_name in reversed(_ADDED_COLUMNS):
        if not inspector.has_table(table_name):
            continue
        columns = {c["name"] for c in inspector.get_columns(table_name)}
        if column_name in columns:
            op.drop_column(table_name, column_name)
