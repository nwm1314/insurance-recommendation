"""auth rbac initial tables

Revision ID: 20260706_0001
Revises:
Create Date: 2026-07-06
"""
from alembic import op

from backend.app.migrations import drop_table_if_created, ensure_tables

revision = "20260706_0001"
down_revision = None
branch_labels = None
depends_on = None

TABLES = [
    "users",
    "roles",
    "permissions",
    "user_roles",
    "role_permissions",
    "refresh_tokens",
    "audit_logs",
    "recommendation_records",
    "saved_profiles",
]


def upgrade():
    ensure_tables(op.get_bind(), TABLES)


def downgrade():
    bind = op.get_bind()
    for name in reversed(TABLES):
        drop_table_if_created(bind, name)
