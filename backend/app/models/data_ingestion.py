from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.database import Base


class SourcePlatform(Base):
    __tablename__ = "source_platforms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    platform_type: Mapped[str] = mapped_column(String(50), default="third_party")
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    robots_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    rate_limit_seconds: Mapped[int] = mapped_column(Integer, default=5)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    pages = relationship("SourcePage", back_populates="platform", cascade="all, delete-orphan")


class SourcePage(Base):
    __tablename__ = "source_pages"
    __table_args__ = (UniqueConstraint("platform_id", "url", name="uq_source_pages_platform_url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform_id: Mapped[int] = mapped_column(Integer, ForeignKey("source_platforms.id"), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    page_type: Mapped[str] = mapped_column(String(50), default="product")
    product_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("products.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    platform = relationship("SourcePlatform", back_populates="pages")


class CrawlJob(Base):
    __tablename__ = "crawl_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_page_id: Mapped[int] = mapped_column(Integer, ForeignKey("source_pages.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="enabled")
    schedule: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CrawlRun(Base):
    __tablename__ = "crawl_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    crawl_job_id: Mapped[int] = mapped_column(Integer, ForeignKey("crawl_jobs.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_document_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("raw_documents.id"), nullable=True)


class RawDocument(Base):
    __tablename__ = "raw_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_page_id: Mapped[int] = mapped_column(Integer, ForeignKey("source_pages.id"), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), default="text/html")
    html: Mapped[str | None] = mapped_column(Text, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    md5_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ExtractionRun(Base):
    __tablename__ = "extraction_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    raw_document_id: Mapped[int] = mapped_column(Integer, ForeignKey("raw_documents.id"), nullable=False)
    extractor: Mapped[str] = mapped_column(String(80), default="llm")
    status: Mapped[str] = mapped_column(String(50), default="pending")
    extracted_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ProductDraft(Base):
    __tablename__ = "product_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    extraction_run_id: Mapped[int] = mapped_column(Integer, ForeignKey("extraction_runs.id"), nullable=False)
    matched_product_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("products.id"), nullable=True)
    draft_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending_review")
    confidence: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ProductVersion(Base):
    __tablename__ = "product_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), nullable=False)
    product_draft_id: Mapped[int] = mapped_column(Integer, ForeignKey("product_drafts.id"), nullable=False)
    version_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    published_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ProductReviewTask(Base):
    __tablename__ = "product_review_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_draft_id: Mapped[int] = mapped_column(Integer, ForeignKey("product_drafts.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    reviewer_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ProductFieldEvidence(Base):
    __tablename__ = "product_field_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_draft_id: Mapped[int] = mapped_column(Integer, ForeignKey("product_drafts.id"), nullable=False)
    field_name: Mapped[str] = mapped_column(String(120), nullable=False)
    field_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
