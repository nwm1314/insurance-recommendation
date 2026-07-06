from sqlalchemy.orm import Session, joinedload

from backend.app.data_ingestion.extractors.product_extractor import extract_product_data
from backend.app.data_ingestion.fetchers.page_fetcher import fetch_source_page
from backend.app.data_ingestion.pipeline import archive_raw_document, create_extraction_review
from backend.app.models.data_ingestion import CrawlJob, CrawlRun, SourcePage
from backend.app.time import utc_now


def execute_crawl_job(db: Session, job: CrawlJob) -> CrawlRun:
    page = db.query(SourcePage).options(joinedload(SourcePage.platform)).filter(SourcePage.id == job.source_page_id).first()
    if page is None:
        raise ValueError("source_page_not_found")

    run = CrawlRun(crawl_job_id=job.id, status="running", started_at=utc_now())
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        fetched = fetch_source_page(page)
        raw = archive_raw_document(db, page, fetched.text, fetched.html)
        extracted_data, confidence, extractor = extract_product_data(fetched.text, fetched.html, page.url)
        task = create_extraction_review(db, raw, extracted_data, confidence, extractor=extractor)

        run.status = "success"
        run.http_status = fetched.http_status
        run.raw_document_id = raw.id
        run.finished_at = utc_now()
        job.status = "enabled"
        db.commit()
        db.refresh(run)
        return run
    except Exception as exc:
        run.status = "failed"
        run.error_message = str(exc)[:2000]
        run.finished_at = utc_now()
        db.commit()
        db.refresh(run)
        return run
