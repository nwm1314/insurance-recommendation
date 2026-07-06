from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.dependencies.auth import get_client_ip, require_permission
from backend.app.models.auth import User
from backend.app.services.auth_service import write_audit_log


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
    write_audit_log(db, user, "admin.crawl.trigger", "crawl_job", detail={"status": "pending"}, ip_address=get_client_ip(request))
    return {"message": "爬虫任务已提交", "status": "pending"}


@router.get("/logs")
def get_logs(user: User = Depends(require_permission("crawl:read"))):
    return {"logs": []}
