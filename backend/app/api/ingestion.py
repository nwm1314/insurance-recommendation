from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.data_ingestion.pipeline import (
    archive_raw_document,
    create_crawl_job,
    create_extraction_review,
    create_source_page,
    list_ingestion_status,
)
from backend.app.data_ingestion.pipelines.crawl_product import execute_crawl_job
from backend.app.data_ingestion.review import approve_review_task, reject_review_task
from backend.app.dependencies.auth import get_client_ip, require_permission
from backend.app.models.auth import User
from backend.app.models.data_ingestion import (
    CrawlJob,
    CrawlRun,
    ExtractionRun,
    ProductDraft,
    ProductFieldEvidence,
    ProductReviewTask,
    RawDocument,
    SourcePage,
    SourcePlatform,
)
from backend.app.services.auth_service import write_audit_log

router = APIRouter(prefix="/api/admin/ingestion", tags=["data-ingestion"])


class SourcePageCreate(BaseModel):
    platform_id: int
    url: str = Field(min_length=8, max_length=1000)
    page_type: str = "product"


class CrawlJobCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    source_page_id: int


class ManualExtractionCreate(BaseModel):
    source_page_id: int
    text: str = Field(min_length=1)
    html: str | None = None
    extracted_data: dict
    confidence: float = Field(default=0.5, ge=0, le=1)


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
    job = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="抓取任务不存在")
    run = execute_crawl_job(db, job)
    write_audit_log(db, user, "ingestion.job.run", "crawl_run", str(run.id), detail={"status": run.status}, ip_address=get_client_ip(request))
    return {"id": run.id, "status": run.status}


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
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "http_status": run.http_status,
            "raw_document_id": run.raw_document_id,
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
    task = approve_review_task(db, task, user.id, payload.note, payload.product_id)
    write_audit_log(db, user, "ingestion.review.approve", "product_review_task", str(task.id), ip_address=get_client_ip(request))
    return {"id": task.id, "status": task.status}


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
