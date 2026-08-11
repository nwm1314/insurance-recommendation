"""data ingestion platform tables

Revision ID: 20260706_0002
Revises: 20260706_0001
Create Date: 2026-07-06
"""
from alembic import op

from backend.app.migrations import drop_table_if_created, ensure_tables

revision = "20260706_0002"
down_revision = "20260706_0001"
branch_labels = None
depends_on = None

CATALOG_TABLES = ["products", "rules", "benefits", "page_logs"]

INGESTION_TABLES = [
    "source_platforms",
    "source_pages",
    "crawl_jobs",
    "raw_documents",
    "crawl_runs",
    "extraction_runs",
    "product_drafts",
    "product_versions",
    "product_review_tasks",
    "product_field_evidence",
]


def upgrade():
    bind = op.get_bind()
    ensure_tables(bind, CATALOG_TABLES)
    ensure_tables(bind, INGESTION_TABLES)


def downgrade():
    bind = op.get_bind()
    for name in reversed(INGESTION_TABLES):
        drop_table_if_created(bind, name)
    for name in ("page_logs", "benefits", "rules", "products"):
        drop_table_if_created(bind, name)
