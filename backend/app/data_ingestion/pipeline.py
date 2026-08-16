import re
from difflib import SequenceMatcher
from sqlalchemy.orm import Session
from backend.app.crawler.scraper import compute_md5
from backend.app.time import utc_now
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

MATCH_FUZZY_RATIO = 0.6


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", "", value or "").lower()


def match_product_for_draft(db: Session, draft_data: dict):
    """Match extracted product data against the existing catalog.

    Exact match: normalized name + company are identical.
    Fuzzy fallback: same type and name similarity >= MATCH_FUZZY_RATIO.
    Returns the matched Product or None.
    """
    from backend.app.models.product import Product

    name = draft_data.get("name")
    if not name:
        return None
    norm_name = _normalize_name(name)
    company = draft_data.get("company")
    norm_company = _normalize_name(company) if company else ""
    product_type = draft_data.get("type")

    best: Product | None = None
    best_ratio = MATCH_FUZZY_RATIO
    for product in db.query(Product).all():
        if _normalize_name(product.name) == norm_name and _normalize_name(product.company) == norm_company:
            return product
        if product_type and product.type == product_type:
            ratio = SequenceMatcher(None, _normalize_name(product.name), norm_name).ratio()
            if ratio >= best_ratio:
                best, best_ratio = product, ratio
    return best

EVIDENCE_FIELDS = [
    "name",
    "company",
    "type",
    "premium_min",
    "premium_max",
    "sum_insured_max",
    "waiting_period_days",
]


def ensure_seed_sources(db: Session):
    """Register the maintained crawl source platforms (idempotent).

    Aggregator sites are the primary product source; insurer official sites are
    supplementary verification sources. zhongmin.cn robots.txt disallows all
    crawling (`Disallow: /`) so it is deactivated, never crawled. Rates follow
    each site's robots.txt (e.g. zhongan Crawl-delay: 60).
    """
    seeds = [
        # name, platform_type, base_url, rate_limit_seconds
        ("慧择网", "third_party", "https://www.huize.com", 10),
        ("开心保", "third_party", "https://www.kaixinbao.com", 10),
        ("深蓝保", "third_party_review", "https://www.shenlanbao.com", 15),
        ("中国平安官网", "official", "https://www.pingan.com", 30),
        ("中国人寿官网", "official", "https://www.e-chinalife.com", 30),
        ("众安保险官网", "official", "https://www.zhongan.com", 65),
    ]
    for name, platform_type, base_url, rate in seeds:
        existing = db.query(SourcePlatform).filter(SourcePlatform.name == name).first()
        if existing is None:
            db.add(SourcePlatform(
                name=name,
                platform_type=platform_type,
                base_url=base_url,
                robots_url=f"{base_url.rstrip('/')}/robots.txt",
                rate_limit_seconds=rate,
            ))
        else:
            existing.platform_type = platform_type
            existing.base_url = base_url
            existing.robots_url = f"{base_url.rstrip('/')}/robots.txt"
            existing.rate_limit_seconds = rate
            existing.is_active = True
    # robots.txt 全站禁止抓取的站点停用（保留历史页面/运行记录供追溯）
    retired = db.query(SourcePlatform).filter(SourcePlatform.name == "中民保险网").first()
    if retired is not None and retired.is_active:
        retired.is_active = False
    db.commit()


def ensure_seed_products_if_empty(db: Session):
    """Seed the demo product catalog on first boot (opt-in).

    The production product pool is built from crawled, reviewed aggregator
    data; the 165-product demo catalog is only seeded when SEED_DEMO_PRODUCTS
    is enabled (local demos / E2E). It must stay off in production so the
    recommendation pool only contains real, traceable products.
    """
    from backend.app.config import settings
    from backend.app.models.product import Product
    if not settings.seed_demo_products:
        return
    if db.query(Product).count() > 0:
        return
    from backend.scripts.seed import seed
    seed()


def create_source_page(db: Session, platform_id: int, url: str, page_type: str = "product") -> SourcePage:
    existing = db.query(SourcePage).filter(SourcePage.platform_id == platform_id, SourcePage.url == url).first()
    if existing:
        return existing
    page = SourcePage(platform_id=platform_id, url=url, page_type=page_type)
    db.add(page)
    db.commit()
    db.refresh(page)
    return page


def create_crawl_job(db: Session, name: str, source_page_id: int, created_by: int | None = None) -> CrawlJob:
    job = CrawlJob(name=name, source_page_id=source_page_id, created_by=created_by)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def create_pending_crawl_run(db: Session, crawl_job_id: int) -> CrawlRun:
    run = CrawlRun(crawl_job_id=crawl_job_id, status="pending")
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def archive_raw_document(db: Session, source_page: SourcePage, text: str, html: str | None = None) -> RawDocument:
    raw = RawDocument(
        source_page_id=source_page.id,
        url=source_page.url,
        html=html,
        text=text,
        md5_hash=compute_md5(text),
    )
    source_page.last_crawled_at = utc_now()
    db.add(raw)
    db.commit()
    db.refresh(raw)
    return raw


def create_extraction_review(
    db: Session,
    raw_document: RawDocument,
    extracted_data: dict,
    confidence: float = 0.5,
    extractor: str = "manual_or_llm",
) -> ProductReviewTask:
    extraction = ExtractionRun(
        raw_document_id=raw_document.id,
        extractor=extractor,
        status="success",
        extracted_data=extracted_data,
        confidence=confidence,
    )
    db.add(extraction)
    db.flush()

    draft = ProductDraft(
        extraction_run_id=extraction.id,
        draft_data=extracted_data,
        status="pending_review",
        confidence=confidence,
    )
    matched = match_product_for_draft(db, extracted_data)
    if matched is not None:
        draft.matched_product_id = matched.id
    db.add(draft)
    db.flush()

    for field in EVIDENCE_FIELDS:
        value = extracted_data.get(field)
        if value is not None:
            db.add(ProductFieldEvidence(
                product_draft_id=draft.id,
                field_name=field,
                field_value=str(value),
                evidence_text=(raw_document.text or "")[:500],
                confidence=confidence,
                source_url=raw_document.url,
            ))

    task = ProductReviewTask(product_draft_id=draft.id, status="pending")
    db.add(task)
    db.commit()
    db.refresh(task)

    # TASK-034: LLM 高置信草稿直接自动发布（带完整性与精确匹配门控 + 审计），
    # 其余留在人工审核队列。失败不影响草稿本身。
    from backend.app.data_ingestion.auto_publish import try_auto_publish
    try_auto_publish(db, task, draft, extractor)

    db.refresh(task)
    return task


def list_ingestion_status(db: Session) -> dict:
    return {
        "source_platforms": db.query(SourcePlatform).count(),
        "source_pages": db.query(SourcePage).count(),
        "crawl_jobs": db.query(CrawlJob).count(),
        "crawl_runs": db.query(CrawlRun).count(),
        "raw_documents": db.query(RawDocument).count(),
        "product_drafts": db.query(ProductDraft).count(),
        "review_tasks": db.query(ProductReviewTask).count(),
    }
