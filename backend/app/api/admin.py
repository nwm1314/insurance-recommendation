from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.dependencies.auth import get_client_ip, require_permission
from backend.app.models.auth import AuditLog, User
from backend.app.models.data_ingestion import CrawlJob, CrawlRun, SourcePage
from backend.app.services.auth_service import write_audit_log
from backend.app.crawler.scheduler import run_crawl_jobs_background
from backend.app.crawler.scraper import validate_url_for_ssrf, SSRFError


router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
)


@router.get("/health")
def health_check(user: User = Depends(require_permission("crawl:read"))):
    return {"status": "ok"}


@router.post("/crawl")
def trigger_crawl(
    request: Request,
    user: User = Depends(require_permission("crawl:trigger")),
    db: Session = Depends(get_db),
):
    """Trigger all enabled crawl jobs immediately in the background.

    The crawl itself runs off the request path (daemon threads with their own
    DB sessions); progress is observable via /api/admin/logs (crawl_runs).
    """
    jobs = db.query(CrawlJob).filter(CrawlJob.status == "enabled").all()
    triggered = []
    skipped = []
    for job in jobs:
        page = db.query(SourcePage).filter(SourcePage.id == job.source_page_id).first()
        if page is not None:
            try:
                validate_url_for_ssrf(page.url)
            except SSRFError:
                skipped.append(job.id)
                continue
        triggered.append(job.id)
    run_crawl_jobs_background(triggered)
    write_audit_log(
        db, user, "admin.crawl.trigger", "crawl_job",
        detail={"triggered": triggered, "skipped": skipped, "count": len(triggered)},
        ip_address=get_client_ip(request),
    )
    return {"message": f"已在后台触发 {len(triggered)} 个抓取任务", "triggered_jobs": triggered, "skipped_jobs": skipped, "status": "started"}


@router.get("/logs")
def get_logs(
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(require_permission("crawl:read")),
    db: Session = Depends(get_db),
):
    audit_logs = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(limit).all()
    crawl_runs = db.query(CrawlRun).order_by(CrawlRun.id.desc()).limit(limit).all()
    return {
        "logs": [
            {
                "id": log.id,
                "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "detail": log.detail,
                "ip_address": log.ip_address,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in audit_logs
        ],
        "crawl_runs": [
            {
                "id": run.id,
                "crawl_job_id": run.crawl_job_id,
                "status": run.status,
                "http_status": run.http_status,
                "error_message": run.error_message,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            }
            for run in crawl_runs
        ],
    }
