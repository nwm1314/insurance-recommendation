from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from typing import Literal
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.crawler.scraper import validate_url_for_ssrf, SSRFError
from backend.app.data_ingestion.pipeline import (
    archive_raw_document,
    create_crawl_job,
    create_extraction_review,
    create_source_page,
    list_ingestion_status,
)
from backend.app.data_ingestion.review import approve_review_task, reject_review_task, rollback_product_version
from backend.app.crawler.scheduler import run_crawl_job_background
from backend.app.dependencies.auth import get_client_ip, require_permission
from backend.app.models.auth import User
from backend.app.models.data_ingestion import (
    CrawlJob,
    CrawlRun,
    ExtractionRun,
    ProductDraft,
    ProductFieldEvidence,
    ProductReviewTask,
    ProductVersion,
    RawDocument,
    SourcePage,
    SourcePlatform,
)
from backend.app.services.auth_service import write_audit_log

router = APIRouter(prefix="/api/admin/ingestion", tags=["data-ingestion"])


class SourcePageCreate(BaseModel):
    platform_id: int
    url: str = Field(min_length=8, max_length=1000)
    page_type: Literal["product", "category", "detail"] = "product"


class CrawlJobCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    source_page_id: int


EXTRACTED_DATA_ALLOWLIST = frozenset({
    "name", "company", "type", "premium_min", "premium_max",
    "sum_insured_min", "sum_insured_max", "coverage_period", "payment_period",
    "source_url", "deductible", "disease_count", "mild_disease_count",
    "moderate_disease_count", "has_mild_coverage", "has_moderate_coverage",
    "has_multi_claim", "min_age", "max_age", "job_class_limit",
    "waiting_period_days", "has_insured_waiver", "has_insurer_waiver",
    "health_disclosure_count", "health_requirements", "benefits", "off_shelf",
})


class ManualExtractionCreate(BaseModel):
    source_page_id: int
    text: str = Field(min_length=1)
    html: str | None = None
    extracted_data: dict
    confidence: float = Field(default=0.5, ge=0, le=1)

    @field_validator("extracted_data")
    @classmethod
    def validate_extracted_data(cls, value: dict) -> dict:
        if not isinstance(value, dict):
            raise ValueError("extracted_data 必须是对象")
        disallowed = set(value.keys()) - EXTRACTED_DATA_ALLOWLIST
        if disallowed:
            raise ValueError(f"extracted_data 包含不允许的字段: {sorted(disallowed)}")
        return value



class SourcePlatformCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    platform_type: Literal["third_party", "official", "aggregator"] = "third_party"
    base_url: str | None = Field(default=None, max_length=500)
    robots_url: str | None = Field(default=None, max_length=500)
    rate_limit_seconds: int = Field(default=5, ge=1, le=60)
    is_active: bool = True


class SourcePlatformUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    platform_type: Literal["third_party", "official", "aggregator"] | None = None
    base_url: str | None = Field(default=None, max_length=500)
    robots_url: str | None = Field(default=None, max_length=500)
    rate_limit_seconds: int | None = Field(default=None, ge=1, le=60)
    is_active: bool | None = None

class ReviewAction(BaseModel):
    note: str | None = Field(default=None, max_length=1000)
    product_id: int | None = None


@router.get("/status")
def ingestion_status(
    user: User = Depends(require_permission("crawl:read")),
    db: Session = Depends(get_db),
):
    return list_ingestion_status(db)


@router.get("/platforms")
def list_platforms(
    user: User = Depends(require_permission("crawl:read")),
    db: Session = Depends(get_db),
):
    platforms = db.query(SourcePlatform).order_by(SourcePlatform.id).all()
    return {"platforms": [
        {
            "id": p.id,
            "name": p.name,
            "platform_type": p.platform_type,
            "base_url": p.base_url,
            "robots_url": p.robots_url,
            "rate_limit_seconds": p.rate_limit_seconds,
            "is_active": p.is_active,
        }
        for p in platforms
    ]}


@router.post("/source-pages")
def add_source_page(
    payload: SourcePageCreate,
    request: Request,
    user: User = Depends(require_permission("crawl:trigger")),
    db: Session = Depends(get_db),
):
    platform = db.query(SourcePlatform).filter(SourcePlatform.id == payload.platform_id).first()
    if platform is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据源平台不存在")
    try:
        validate_url_for_ssrf(payload.url)
    except SSRFError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"URL被拒绝（SSRF防护）: {exc}") from exc
    page = create_source_page(db, payload.platform_id, payload.url, payload.page_type)
    write_audit_log(db, user, "ingestion.source_page.create", "source_page", str(page.id), ip_address=get_client_ip(request))
    return {"id": page.id, "url": page.url}


@router.get("/source-pages")
def list_source_pages(
    user: User = Depends(require_permission("crawl:read")),
    db: Session = Depends(get_db),
):
    pages = db.query(SourcePage).order_by(SourcePage.id.desc()).limit(100).all()
    return {"pages": [
        {
            "id": page.id,
            "platform_id": page.platform_id,
            "url": page.url,
            "page_type": page.page_type,
            "is_active": page.is_active,
            "last_crawled_at": page.last_crawled_at.isoformat() if page.last_crawled_at else None,
        }
        for page in pages
    ]}


@router.post("/jobs")
def add_crawl_job(
    payload: CrawlJobCreate,
    request: Request,
    user: User = Depends(require_permission("crawl:trigger")),
    db: Session = Depends(get_db),
):
    page = db.query(SourcePage).filter(SourcePage.id == payload.source_page_id).first()
    if page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据源页面不存在")
    job = create_crawl_job(db, payload.name, payload.source_page_id, user.id)
    write_audit_log(db, user, "ingestion.job.create", "crawl_job", str(job.id), ip_address=get_client_ip(request))
    return {"id": job.id, "name": job.name, "status": job.status}


@router.get("/jobs")
def list_crawl_jobs(
    user: User = Depends(require_permission("crawl:read")),
    db: Session = Depends(get_db),
):
    jobs = db.query(CrawlJob).order_by(CrawlJob.id.desc()).limit(100).all()
    return {"jobs": [
        {"id": job.id, "name": job.name, "source_page_id": job.source_page_id, "status": job.status}
        for job in jobs
    ]}


@router.post("/jobs/{job_id}/run")
def run_crawl_job(
    job_id: int,
    request: Request,
    user: User = Depends(require_permission("crawl:trigger")),
    db: Session = Depends(get_db),
):
    """Trigger a crawl job in the background and return immediately.

    Long crawl jobs run off the request path (daemon thread with its own DB
    session); the run status is observable via GET /api/admin/ingestion/runs.
    """
    job = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    page = db.query(SourcePage).filter(SourcePage.id == job.source_page_id).first()
    if page is not None:
        try:
            validate_url_for_ssrf(page.url)
        except SSRFError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"URL被拒绝（SSRF防护）: {exc}") from exc
    run_crawl_job_background(job_id)
    write_audit_log(db, user, "ingestion.job.run", "crawl_job", str(job_id), ip_address=get_client_ip(request))
    return {"id": job_id, "status": "started", "message": "抓取任务已在后台启动，可通过抓取记录查看进度"}


@router.get("/runs")
def list_crawl_runs(
    user: User = Depends(require_permission("crawl:read")),
    db: Session = Depends(get_db),
):
    runs = db.query(CrawlRun).order_by(CrawlRun.id.desc()).limit(100).all()
    return {"runs": [
        {
            "id": run.id,
            "crawl_job_id": run.crawl_job_id,
            "status": run.status,
            "http_status": run.http_status,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "error_message": run.error_message,
        }
        for run in runs
    ]}


@router.post("/manual-extractions")
def create_manual_extraction(
    payload: ManualExtractionCreate,
    request: Request,
    user: User = Depends(require_permission("crawl:trigger")),
    db: Session = Depends(get_db),
):
    page = db.query(SourcePage).filter(SourcePage.id == payload.source_page_id).first()
    if page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据源页面不存在")
    raw = archive_raw_document(db, page, payload.text, payload.html)
    task = create_extraction_review(db, raw, payload.extracted_data, payload.confidence)
    write_audit_log(db, user, "ingestion.extraction.review_created", "product_review_task", str(task.id), ip_address=get_client_ip(request))
    return {"review_task_id": task.id, "status": task.status}


@router.get("/review-tasks")
def list_review_tasks(
    user: User = Depends(require_permission("review:read")),
    db: Session = Depends(get_db),
):
    tasks = db.query(ProductReviewTask).order_by(ProductReviewTask.id.desc()).limit(100).all()
    def serialize_task(task: ProductReviewTask):
        draft = db.query(ProductDraft).filter(ProductDraft.id == task.product_draft_id).first()
        return {
            "id": task.id,
            "product_draft_id": task.product_draft_id,
            "status": task.status,
            "reviewer_id": task.reviewer_id,
            "review_note": task.review_note,
            "draft_name": (draft.draft_data or {}).get("name") if draft else None,
            "draft_type": (draft.draft_data or {}).get("type") if draft else None,
            "off_shelf": bool((draft.draft_data or {}).get("off_shelf")) if draft else False,
            "matched_product_id": draft.matched_product_id if draft else None,
            "confidence": draft.confidence if draft else None,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "reviewed_at": task.reviewed_at.isoformat() if task.reviewed_at else None,
        }

    return {"tasks": [serialize_task(task) for task in tasks]}


@router.get("/review-tasks/{task_id}")
def get_review_task(
    task_id: int,
    user: User = Depends(require_permission("review:read")),
    db: Session = Depends(get_db),
):
    task = db.query(ProductReviewTask).filter(ProductReviewTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="审核任务不存在")
    draft = db.query(ProductDraft).filter(ProductDraft.id == task.product_draft_id).first()
    evidence = db.query(ProductFieldEvidence).filter(ProductFieldEvidence.product_draft_id == task.product_draft_id).all()
    raw = None
    if draft:
        extraction = db.query(ExtractionRun).filter(ExtractionRun.id == draft.extraction_run_id).first()
        if extraction:
            raw = db.query(RawDocument).filter(RawDocument.id == extraction.raw_document_id).first()
    return {
        "id": task.id,
        "status": task.status,
        "review_note": task.review_note,
        "draft": draft.draft_data if draft else None,
        "confidence": draft.confidence if draft else None,
        "evidence": [
            {
                "field_name": item.field_name,
                "field_value": item.field_value,
                "evidence_text": item.evidence_text,
                "confidence": item.confidence,
                "source_url": item.source_url,
            }
            for item in evidence
        ],
        "raw_document_id": raw.id if raw else None,
    }


@router.post("/review-tasks/{task_id}/approve")
def approve_task(
    task_id: int,
    payload: ReviewAction,
    request: Request,
    user: User = Depends(require_permission("review:approve")),
    db: Session = Depends(get_db),
):
    task = db.query(ProductReviewTask).filter(ProductReviewTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="审核任务不存在")
    try:
        task = approve_review_task(db, task, user.id, payload.note, payload.product_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"审批失败: {exc}") from exc
    draft = db.query(ProductDraft).filter(ProductDraft.id == task.product_draft_id).first()
    version = (
        db.query(ProductVersion)
        .filter(ProductVersion.product_draft_id == task.product_draft_id)
        .order_by(ProductVersion.id.desc())
        .first()
    )
    write_audit_log(db, user, "ingestion.review.approve", "product_review_task", str(task.id),
                    detail={"product_id": draft.matched_product_id if draft else None,
                            "version_id": version.id if version else None},
                    ip_address=get_client_ip(request))
    return {
        "id": task.id,
        "status": task.status,
        "product_id": draft.matched_product_id if draft else None,
        "version_id": version.id if version else None,
    }


@router.post("/review-tasks/{task_id}/reject")
def reject_task(
    task_id: int,
    payload: ReviewAction,
    request: Request,
    user: User = Depends(require_permission("review:approve")),
    db: Session = Depends(get_db),
):
    task = db.query(ProductReviewTask).filter(ProductReviewTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="审核任务不存在")
    task = reject_review_task(db, task, user.id, payload.note)
    write_audit_log(db, user, "ingestion.review.reject", "product_review_task", str(task.id), ip_address=get_client_ip(request))
    return {"id": task.id, "status": task.status}


@router.get("/versions")
def list_versions(
    product_id: int | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(require_permission("review:read")),
    db: Session = Depends(get_db),
):
    query = db.query(ProductVersion).order_by(ProductVersion.id.desc())
    if product_id is not None:
        query = query.filter(ProductVersion.product_id == product_id)
    versions = query.limit(limit).all()
    return {"versions": [
        {
            "id": v.id,
            "product_id": v.product_id,
            "product_draft_id": v.product_draft_id,
            "published_by": v.published_by,
            "off_shelf": bool((v.version_data or {}).get("off_shelf")),
            "name": (v.version_data or {}).get("name"),
            "company": (v.version_data or {}).get("company"),
            "type": (v.version_data or {}).get("type"),
            "published_at": v.published_at.isoformat() if v.published_at else None,
        }
        for v in versions
    ]}


@router.post("/versions/{version_id}/rollback")
def rollback_version(
    version_id: int,
    request: Request,
    user: User = Depends(require_permission("review:approve")),
    db: Session = Depends(get_db),
):
    version = db.query(ProductVersion).filter(ProductVersion.id == version_id).first()
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="版本不存在")
    try:
        product = rollback_product_version(db, version)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"回滚失败: {exc}") from exc
    write_audit_log(db, user, "ingestion.version.rollback", "product_version", str(version.id),
                    detail={"product_id": product.id, "name": product.name}, ip_address=get_client_ip(request))
    return {"status": "ok", "product_id": product.id, "message": "已回滚"}


@router.get("/products/{product_id}/provenance")
def get_product_provenance(
    product_id: int,
    user: User = Depends(require_permission("review:read")),
    db: Session = Depends(get_db),
):
    """Return the source history and freshness of a published product.

    Combines the source pages that fed its drafts (with last_crawled_at as the
    last verification time) and the published version history, so the catalog
    record is traceable back to its original source.
    """
    from backend.app.models.product import Product

    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="产品不存在")

    drafts = db.query(ProductDraft).filter(ProductDraft.matched_product_id == product_id).all()
    source_page_ids: set[int] = set()
    for draft in drafts:
        extraction = db.query(ExtractionRun).filter(ExtractionRun.id == draft.extraction_run_id).first()
        if extraction is None:
            continue
        raw = db.query(RawDocument).filter(RawDocument.id == extraction.raw_document_id).first()
        if raw is not None:
            source_page_ids.add(raw.source_page_id)
    pages = (
        db.query(SourcePage)
        .filter(SourcePage.id.in_(source_page_ids))
        .order_by(SourcePage.id)
        .all()
        if source_page_ids
        else []
    )
    versions = (
        db.query(ProductVersion)
        .filter(ProductVersion.product_id == product_id)
        .order_by(ProductVersion.id.desc())
        .limit(50)
        .all()
    )
    last_crawled = [p.last_crawled_at for p in pages if p.last_crawled_at]
    return {
        "product_id": product.id,
        "name": product.name,
        "company": product.company,
        "type": product.type,
        "status": product.status,
        "source_url": product.source_url,
        "updated_at": product.updated_at.isoformat() if product.updated_at else None,
        "last_verified_at": max(last_crawled).isoformat() if last_crawled else None,
        "source_pages": [
            {
                "id": page.id,
                "url": page.url,
                "platform": page.platform.name if page.platform else None,
                "last_crawled_at": page.last_crawled_at.isoformat() if page.last_crawled_at else None,
            }
            for page in pages
        ],
        "versions": [
            {
                "id": version.id,
                "product_draft_id": version.product_draft_id,
                "published_by": version.published_by,
                "published_at": version.published_at.isoformat() if version.published_at else None,
                "off_shelf": bool((version.version_data or {}).get("off_shelf")),
                "name": (version.version_data or {}).get("name"),
                "company": (version.version_data or {}).get("company"),
                "type": (version.version_data or {}).get("type"),
            }
            for version in versions
        ],
    }



@router.post("/platforms")
def create_platform(
    payload: SourcePlatformCreate,
    request: Request,
    user: User = Depends(require_permission("crawl:trigger")),
    db: Session = Depends(get_db),
):
    existing = db.query(SourcePlatform).filter(SourcePlatform.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="数据源平台已存在")
    platform = SourcePlatform(**payload.model_dump())
    db.add(platform)
    db.commit()
    db.refresh(platform)
    write_audit_log(db, user, "ingestion.platform.create", "source_platform", str(platform.id), ip_address=get_client_ip(request))
    return {
        "id": platform.id, "name": platform.name, "platform_type": platform.platform_type,
        "base_url": platform.base_url, "robots_url": platform.robots_url,
        "rate_limit_seconds": platform.rate_limit_seconds, "is_active": platform.is_active,
    }


@router.put("/platforms/{platform_id}")
def update_platform(
    platform_id: int,
    payload: SourcePlatformUpdate,
    request: Request,
    user: User = Depends(require_permission("crawl:trigger")),
    db: Session = Depends(get_db),
):
    platform = db.query(SourcePlatform).filter(SourcePlatform.id == platform_id).first()
    if not platform:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据源平台不存在")
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    for key, value in data.items():
        setattr(platform, key, value)
    db.commit()
    db.refresh(platform)
    write_audit_log(db, user, "ingestion.platform.update", "source_platform", str(platform.id), ip_address=get_client_ip(request))
    return {
        "id": platform.id, "name": platform.name, "platform_type": platform.platform_type,
        "base_url": platform.base_url, "robots_url": platform.robots_url,
        "rate_limit_seconds": platform.rate_limit_seconds, "is_active": platform.is_active,
    }


@router.delete("/platforms/{platform_id}")
def delete_platform(
    platform_id: int,
    request: Request,
    user: User = Depends(require_permission("crawl:trigger")),
    db: Session = Depends(get_db),
):
    platform = db.query(SourcePlatform).filter(SourcePlatform.id == platform_id).first()
    if not platform:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据源平台不存在")
    db.delete(platform)
    db.commit()
    write_audit_log(db, user, "ingestion.platform.delete", "source_platform", str(platform.id), ip_address=get_client_ip(request))
    return {"status": "ok", "message": "数据源平台已删除"}
