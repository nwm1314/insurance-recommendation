"""data ingestion platform tables

Revision ID: 20260706_0002
Revises: 20260706_0001
Create Date: 2026-07-06
"""
from alembic import op
import sqlalchemy as sa

revision = "20260706_0002"
down_revision = "20260706_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "source_platforms",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=120), nullable=False, unique=True),
        sa.Column("platform_type", sa.String(length=50), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=True),
        sa.Column("robots_url", sa.String(length=500), nullable=True),
        sa.Column("rate_limit_seconds", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "source_pages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("platform_id", sa.Integer(), sa.ForeignKey("source_platforms.id"), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("page_type", sa.String(length=50), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_crawled_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("platform_id", "url", name="uq_source_pages_platform_url"),
    )
    op.create_table(
        "crawl_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("source_page_id", sa.Integer(), sa.ForeignKey("source_pages.id"), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("schedule", sa.String(length=120), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "raw_documents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_page_id", sa.Integer(), sa.ForeignKey("source_pages.id"), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("html", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("md5_hash", sa.String(length=32), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "crawl_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("crawl_job_id", sa.Integer(), sa.ForeignKey("crawl_jobs.id"), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("raw_document_id", sa.Integer(), sa.ForeignKey("raw_documents.id"), nullable=True),
    )
    op.create_table(
        "extraction_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("raw_document_id", sa.Integer(), sa.ForeignKey("raw_documents.id"), nullable=False),
        sa.Column("extractor", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("extracted_data", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "product_drafts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("extraction_run_id", sa.Integer(), sa.ForeignKey("extraction_runs.id"), nullable=False),
        sa.Column("matched_product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=True),
        sa.Column("draft_data", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "product_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("product_draft_id", sa.Integer(), sa.ForeignKey("product_drafts.id"), nullable=False),
        sa.Column("version_data", sa.JSON(), nullable=False),
        sa.Column("published_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("published_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "product_review_tasks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("product_draft_id", sa.Integer(), sa.ForeignKey("product_drafts.id"), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "product_field_evidence",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("product_draft_id", sa.Integer(), sa.ForeignKey("product_drafts.id"), nullable=False),
        sa.Column("field_name", sa.String(length=120), nullable=False),
        sa.Column("field_value", sa.Text(), nullable=True),
        sa.Column("evidence_text", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
    )


def downgrade():
    op.drop_table("product_field_evidence")
    op.drop_table("product_review_tasks")
    op.drop_table("product_versions")
    op.drop_table("product_drafts")
    op.drop_table("extraction_runs")
    op.drop_table("crawl_runs")
    op.drop_table("raw_documents")
    op.drop_table("crawl_jobs")
    op.drop_table("source_pages")
    op.drop_table("source_platforms")
