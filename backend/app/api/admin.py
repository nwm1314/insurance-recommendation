from fastapi import APIRouter

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/health")
def health_check():
    return {"status": "ok"}


@router.post("/crawl")
def trigger_crawl():
    return {"message": "爬虫任务已提交", "status": "pending"}


@router.get("/logs")
def get_logs():
    return {"logs": []}
