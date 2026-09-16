"""product_versions.product_draft_id nullable for admin-edit snapshots (DATA-003)

Revision ID: 20260914_0002
Revises: 20260914_0001
Create Date: 2026-09-14
"""
from alembic import op
import sqlalchemy as sa

from backend.app.migrations import ALL_TABLE_NAMES, align_columns, align_indexes, ensure_tables

revision = "20260914_0002"
down_revision = "20260914_0001"
branch_labels = None
depends_on = None

_ADDED_COLUMNS: list[tuple[str, str]] = []


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    missing_tables = [n for n in ALL_TABLE_NAMES if not inspector.has_table(n)]
    ensure_tables(bind, missing_tables)
    # 管理员编辑入版本链：编辑产生的版本没有草稿，放宽外键非空约束
    if inspector.has_table("product_versions"):
        columns = {c["name"]: c for c in inspector.get_columns("product_versions")}
        if "product_draft_id" in columns and columns["product_draft_id"].get("nullable", True) is False:
            with op.batch_alter_table("product_versions") as batch_op:
                batch_op.alter_column(
                    "product_draft_id", existing_type=sa.Integer(), nullable=True,
                )
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
    # 不恢复 NOT NULL：存量数据可能已包含无草稿的管理员编辑版本
