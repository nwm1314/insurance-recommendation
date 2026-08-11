from sqlalchemy.orm import Session, joinedload

from backend.app.crawler.scraper import compute_md5, detect_off_shelf
from backend.app.data_ingestion.extractors.product_extractor import extract_product_data
from backend.app.data_ingestion.fetchers.page_fetcher import fetch_source_page
from backend.app.data_ingestion.pipeline import archive_raw_document, create_extraction_review
from backend.app.models.data_ingestion import CrawlJob, CrawlRun, ExtractionRun, ProductDraft, RawDocument, SourcePage
from backend.app.time import utc_now

OFF_SHELF_HTTP_STATUSES = {404, 410}


def _last_raw_document(db: Session, source_page_id: int) -> RawDocument | None:
    return (
        db.query(RawDocument)
        .filter(RawDocument.source_page_id == source_page_id)
        .order_by(RawDocument.id.desc())
        .first()
    )


def _last_draft_identity(db: Session, source_page_id: int) -> dict:
    """Return the name/company/type of the most recent draft for a source page.

    Used when a page disappears (404/410) so the off-shelf draft can still be
    matched to the product that was previously known for that URL.
    """
    last_raw = _last_raw_document(db, source_page_id)
    if last_raw is None:
        return {}
    extraction = (
        db.query(ExtractionRun)
        .filter(ExtractionRun.raw_document_id == last_raw.id)
        .order_by(ExtractionRun.id.desc())
        .first()
    )
    if extraction is None:
        return {}
    draft = (
        db.query(ProductDraft)
        .filter(ProductDraft.extraction_run_id == extraction.id)
        .order_by(ProductDraft.id.desc())
        .first()
    )
    if draft is None:
        return {}
    data = draft.draft_data or {}
    return {key: data[key] for key in ("name", "company", "type") if data.get(key)}


def _is_off_shelf(fetched) -> bool:
    if detect_off_shelf(fetched.text or ""):
        return True
    if fetched.http_status in OFF_SHELF_HTTP_STATUSES:
        return True
    if not (fetched.text or ""):
        return True
    return False


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
        off_shelf = _is_off_shelf(fetched)
        md5 = compute_md5(fetched.text or "")
        last_raw = _last_raw_document(db, page.id)
        if not off_shelf and last_raw is not None and last_raw.md5_hash == md5:
            page.last_crawled_at = utc_now()
            run.status = "skipped"
            run.http_status = fetched.http_status
            run.error_message = "unchanged_md5"
            run.finished_at = utc_now()
            db.commit()
            db.refresh(run)
            return run

        if off_shelf and not (fetched.text or ""):
            extracted_data = {"off_shelf": True}
            extracted_data.update(_last_draft_identity(db, page.id))
            confidence, extractor = 1.0, "off_shelf_detector"
        else:
            extracted_data, confidence, extractor = extract_product_data(fetched.text, fetched.html, page.url)
            if off_shelf:
                extracted_data["off_shelf"] = True
                fallback = _last_draft_identity(db, page.id)
                for key in ("name", "company", "type"):
                    if not extracted_data.get(key) and fallback.get(key):
                        extracted_data[key] = fallback[key]
        raw = archive_raw_document(db, page, fetched.text, fetched.html)
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
