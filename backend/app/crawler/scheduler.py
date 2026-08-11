import logging
import os
import threading

from apscheduler.schedulers.background import BackgroundScheduler

from backend.app.database import SessionLocal
from backend.app.data_ingestion.pipelines.crawl_product import execute_crawl_job
from backend.app.models.data_ingestion import CrawlJob, CrawlRun
from backend.app.time import utc_now

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()

CRAWL_JOB_ID = "crawl_all_enabled_jobs"
DEFAULT_INTERVAL_MINUTES = 720


def crawl_interval_minutes() -> int:
    raw = os.environ.get("CRAWL_INTERVAL_MINUTES", str(DEFAULT_INTERVAL_MINUTES))
    try:
        return max(int(raw), 1)
    except ValueError:
        return DEFAULT_INTERVAL_MINUTES


def run_all_enabled_jobs() -> dict:
    """Run every enabled crawl job once; each failure is recorded in CrawlRun."""
    db = SessionLocal()
    triggered: list[int] = []
    failed: list[int] = []
    skipped: list[int] = []
    try:
        jobs = db.query(CrawlJob).filter(CrawlJob.status == "enabled").all()
        for job in jobs:
            try:
                run = execute_crawl_job(db, job)
                if run.status == "failed":
                    failed.append(job.id)
                elif run.status == "skipped":
                    skipped.append(job.id)
                else:
                    triggered.append(job.id)
            except Exception as exc:
                failed.append(job.id)
                logger.exception("scheduled crawl job %s failed", job.id, exc_info=exc)
    finally:
        db.close()
    return {"triggered": triggered, "skipped": skipped, "failed": failed}


def register_crawl_jobs() -> None:
    """Register the periodic crawl job (interval from CRAWL_INTERVAL_MINUTES)."""
    scheduler.add_job(
        run_all_enabled_jobs,
        "interval",
        minutes=crawl_interval_minutes(),
        id=CRAWL_JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )


def init_scheduler() -> None:
    """Initialize scheduled tasks: periodic crawl of all enabled jobs."""
    if scheduler.running:
        return
    register_crawl_jobs()
    scheduler.start()


def _record_failed_run(db, job_id: int, message: str) -> None:
    """Best-effort record of a failed run when the job pipeline crashed
    before it could write its own CrawlRun row."""
    try:
        db.add(CrawlRun(
            crawl_job_id=job_id,
            status="failed",
            started_at=utc_now(),
            finished_at=utc_now(),
            error_message=str(message)[:2000],
        ))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("failed to record crawl failure for job %s", job_id)


def _background_worker(job_id: int) -> None:
    """Run a single crawl job in a daemon thread with its own DB session.

    Long crawl jobs (network fetch + extraction) run off the request path so
    that API requests return immediately; progress is observable through the
    CrawlRun rows written by execute_crawl_job.
    """
    db = SessionLocal()
    try:
        job = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
        if job is None:
            logger.warning("background crawl job %s no longer exists", job_id)
            return
        try:
            execute_crawl_job(db, job)
        except Exception as exc:
            logger.exception("background crawl job %s failed", job_id)
            _record_failed_run(db, job_id, exc)
    finally:
        db.close()


def run_crawl_job_background(job_id: int) -> None:
    """Trigger a single crawl job in the background; returns immediately."""
    threading.Thread(
        target=_background_worker,
        args=(job_id,),
        daemon=True,
        name=f"crawl-job-{job_id}",
    ).start()


def run_crawl_jobs_background(job_ids: list[int]) -> None:
    """Trigger several crawl jobs in the background; returns immediately."""
    for job_id in job_ids:
        run_crawl_job_background(job_id)
