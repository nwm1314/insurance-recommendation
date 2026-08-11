import os
import sys
import tempfile
import time
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(tempfile.gettempdir(), 'insurance_review_workflow_pytest.db').replace(os.sep, '/')}",
)
os.environ.setdefault("DISABLE_SCHEDULER_IN_TESTS", "true")

try:
    os.remove(os.path.join(tempfile.gettempdir(), "insurance_review_workflow_pytest.db"))
except OSError:
    pass

import pytest
from fastapi.testclient import TestClient

import backend.app.crawler.scheduler as scheduler_module
import backend.app.data_ingestion.pipelines.crawl_product as crawl_product_pipeline
from backend.app.data_ingestion.fetchers.page_fetcher import FetchResult
from backend.main import app
from backend.app.config import settings
from backend.app.database import SessionLocal
from backend.app.models.auth import AuditLog, RecommendationRecord, RefreshToken, SavedProfile, User, UserRole
from backend.app.models.benefit import Benefit
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
from backend.app.models.product import Product
from backend.app.models.rule import Rule
from backend.app.services.auth_service import ensure_auth_defaults


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clean_data():
    _clean()
    yield
    _clean()


def _clean():
    from sqlalchemy import inspect

    db = SessionLocal()
    try:
        if "product_field_evidence" not in set(inspect(db.get_bind()).get_table_names()):
            return
        db.query(ProductFieldEvidence).delete()
        db.query(ProductReviewTask).delete()
        db.query(ProductVersion).delete()
        db.query(ProductDraft).delete()
        db.query(ExtractionRun).delete()
        db.query(CrawlRun).delete()
        db.query(RawDocument).delete()
        db.query(CrawlJob).delete()
        db.query(SourcePage).delete()
        db.query(AuditLog).delete()
        db.query(RecommendationRecord).delete()
        db.query(SavedProfile).delete()
        db.query(RefreshToken).delete()
        db.query(UserRole).delete()
        db.query(User).delete()
        db.query(Benefit).delete()
        db.query(Rule).delete()
        db.query(Product).delete()
        db.commit()
    finally:
        db.close()


def _bootstrap_admin(monkeypatch):
    monkeypatch.setattr(settings, "first_admin_email", "flow-admin@example.com")
    monkeypatch.setattr(settings, "first_admin_password", "Password12345")
    db = SessionLocal()
    try:
        ensure_auth_defaults(db)
    finally:
        db.close()


def _register(client, email, password="Password12345"):
    response = client.post("/api/auth/register", json={"email": email, "password": password, "full_name": email})
    assert response.status_code == 200, response.text
    return response.json()


def _login_token(client, email, password="Password12345"):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return client.cookies.get("access_token")


@pytest.fixture()
def admin_headers(client, monkeypatch):
    _bootstrap_admin(monkeypatch)
    token = _login_token(client, "flow-admin@example.com")
    client.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


def _first_platform_id(client, headers) -> int:
    platforms = client.get("/api/admin/ingestion/platforms", headers=headers)
    assert platforms.status_code == 200, platforms.text
    return platforms.json()["platforms"][0]["id"]


def _create_page_and_job(client, headers, url=None) -> tuple[int, int]:
    platform_id = _first_platform_id(client, headers)
    page = client.post(
        "/api/admin/ingestion/source-pages",
        headers=headers,
        json={
            "platform_id": platform_id,
            "url": url or f"https://example.com/flow-{uuid.uuid4().hex[:8]}",
            "page_type": "product",
        },
    )
    assert page.status_code == 200, page.text
    page_id = page.json()["id"]
    job = client.post(
        "/api/admin/ingestion/jobs",
        headers=headers,
        json={"name": "flow job", "source_page_id": page_id},
    )
    assert job.status_code == 200, job.text
    return page_id, job.json()["id"]


def _create_page_direct(db, url=None) -> SourcePage:
    platform = db.query(SourcePlatform).order_by(SourcePlatform.id).first()
    assert platform is not None, "seed platforms missing"
    page = SourcePage(platform_id=platform.id, url=url or f"https://example.com/direct-{uuid.uuid4().hex[:8]}", page_type="product")
    db.add(page)
    db.commit()
    db.refresh(page)
    return page


def _wait_for_run(db, job_id: int, timeout: float = 5.0) -> CrawlRun | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = (
            db.query(CrawlRun)
            .filter(CrawlRun.crawl_job_id == job_id)
            .order_by(CrawlRun.id.desc())
            .first()
        )
        if run is not None and run.status in ("success", "failed", "skipped"):
            return run
        time.sleep(0.02)
    return None


def _make_fetch(text: str, http_status: int = 200, html: str | None = None):
    def fake_fetch(source_page):
        return FetchResult(text=text, html=html, http_status=http_status)
    return fake_fetch


def _make_extract(data: dict, confidence: float = 0.9):
    def fake_extract(text, html, url):
        return dict(data), confidence, "pytest_fake"
    return fake_extract


# ---------------------------------------------------------------------------
# 定时调度
# ---------------------------------------------------------------------------

def test_scheduler_registers_interval_job_idempotently(monkeypatch):
    if scheduler_module.scheduler.running:
        scheduler_module.scheduler.shutdown(wait=False)
    try:
        scheduler_module.scheduler.remove_job(scheduler_module.CRAWL_JOB_ID)
    except Exception:
        pass

    monkeypatch.setenv("CRAWL_INTERVAL_MINUTES", "123")
    scheduler_module.register_crawl_jobs()
    scheduler_module.init_scheduler()
    assert scheduler_module.scheduler.running

    job = scheduler_module.scheduler.get_job(scheduler_module.CRAWL_JOB_ID)
    assert job is not None
    assert job.trigger.interval.total_seconds() == 123 * 60

    # re-registration while running replaces the existing job (single instance)
    scheduler_module.register_crawl_jobs()
    matches = [j for j in scheduler_module.scheduler.get_jobs() if j.id == scheduler_module.CRAWL_JOB_ID]
    assert len(matches) == 1, "interval job must not be registered twice"

    # init_scheduler is idempotent once running
    scheduler_module.init_scheduler()
    assert scheduler_module.scheduler.running
    scheduler_module.scheduler.shutdown(wait=False)


def test_scheduler_run_all_enabled_jobs_outcomes(client, monkeypatch):
    db = SessionLocal()
    try:
        job_success = CrawlJob(name="ok", source_page_id=_create_page_direct(db).id)
        job_skipped = CrawlJob(name="skip", source_page_id=_create_page_direct(db).id)
        job_failed = CrawlJob(name="fail", source_page_id=_create_page_direct(db).id)
        db.add_all([job_success, job_skipped, job_failed])
        db.commit()

        def fake_execute(db_session, crawl_job):
            status = {"ok": "success", "skip": "skipped", "fail": "failed"}[crawl_job.name]
            run = CrawlRun(crawl_job_id=crawl_job.id, status=status, http_status=200)
            db_session.add(run)
            db_session.commit()
            db_session.refresh(run)
            return run

        monkeypatch.setattr(scheduler_module, "execute_crawl_job", fake_execute)
        result = scheduler_module.run_all_enabled_jobs()
        assert sorted(result["triggered"]) == sorted([job_success.id])
        assert sorted(result["skipped"]) == sorted([job_skipped.id])
        assert sorted(result["failed"]) == sorted([job_failed.id])
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 手动触发：后台执行、不阻塞请求
# ---------------------------------------------------------------------------

def test_manual_job_run_is_background_and_non_blocking(client, admin_headers, monkeypatch):
    page_id, job_id = _create_page_and_job(client, admin_headers)

    def slow_execute(db, crawl_job):
        time.sleep(0.6)
        run = CrawlRun(crawl_job_id=crawl_job.id, status="success", http_status=200)
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    monkeypatch.setattr(scheduler_module, "execute_crawl_job", slow_execute)

    db = SessionLocal()
    try:
        start = time.monotonic()
        response = client.post(f"/api/admin/ingestion/jobs/{job_id}/run", headers=admin_headers)
        elapsed = time.monotonic() - start
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "started"
        assert body["id"] == job_id
        assert elapsed < 0.5, "long crawl job must not block the API request"

        run = _wait_for_run(db, job_id)
        assert run is not None, "background crawl run did not finish in time"
        assert run.status == "success"
        assert run.http_status == 200

        runs_listing = client.get("/api/admin/ingestion/runs", headers=admin_headers)
        assert runs_listing.status_code == 200, runs_listing.text
        assert any(r["crawl_job_id"] == job_id for r in runs_listing.json()["runs"])
    finally:
        db.close()


def test_admin_crawl_trigger_is_background(client, admin_headers, monkeypatch):
    _page_id, job_id = _create_page_and_job(client, admin_headers)

    def slow_execute(db, crawl_job):
        time.sleep(0.4)
        run = CrawlRun(crawl_job_id=crawl_job.id, status="success", http_status=200)
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    monkeypatch.setattr(scheduler_module, "execute_crawl_job", slow_execute)

    db = SessionLocal()
    try:
        start = time.monotonic()
        response = client.post("/api/admin/crawl", headers=admin_headers)
        elapsed = time.monotonic() - start
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "started"
        assert job_id in body["triggered_jobs"]
        assert elapsed < 0.3, "bulk crawl trigger must not block the API request"
        run = _wait_for_run(db, job_id)
        assert run is not None and run.status == "success"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 增量检测：未变更（MD5 相同）跳过、变更产生新审核任务
# ---------------------------------------------------------------------------

def test_crawl_unchanged_md5_skips(client, admin_headers, monkeypatch):
    page_id, job_id = _create_page_and_job(client, admin_headers)

    db = SessionLocal()
    try:
        page_obj = db.query(SourcePage).filter(SourcePage.id == page_id).first()
        job = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
        text = "同一内容 医疗险 保费500元 保额300万"

        monkeypatch.setattr(crawl_product_pipeline, "fetch_source_page", _make_fetch(text))
        monkeypatch.setattr(
            crawl_product_pipeline, "extract_product_data",
            _make_extract({"name": "增量产品", "company": "增量公司", "type": "医疗险", "premium_min": 500}),
        )

        first = crawl_product_pipeline.execute_crawl_job(db, job)
        assert first.status == "success"
        assert first.raw_document_id is not None
        assert db.query(RawDocument).count() == 1
        first_crawled_at = page_obj.last_crawled_at

        second = crawl_product_pipeline.execute_crawl_job(db, job)
        assert second.status == "skipped"
        assert second.error_message == "unchanged_md5"
        assert db.query(RawDocument).count() == 1, "unchanged content must not be re-archived"
        assert db.query(ProductDraft).count() == 1, "unchanged content must not create new drafts"
        assert page_obj.last_crawled_at is not None
        assert page_obj.last_crawled_at >= first_crawled_at
    finally:
        db.close()


def test_crawl_changed_content_creates_new_review(client, admin_headers, monkeypatch):
    _page_id, job_id = _create_page_and_job(client, admin_headers)

    db = SessionLocal()
    try:
        job = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
        monkeypatch.setattr(crawl_product_pipeline, "fetch_source_page", _make_fetch("版本一内容 医疗险"))
        monkeypatch.setattr(
            crawl_product_pipeline, "extract_product_data",
            _make_extract({"name": "变更产品", "company": "变更公司", "type": "医疗险", "premium_min": 500}),
        )
        first = crawl_product_pipeline.execute_crawl_job(db, job)
        assert first.status == "success"

        monkeypatch.setattr(crawl_product_pipeline, "fetch_source_page", _make_fetch("版本二内容 医疗险 保费600"))
        monkeypatch.setattr(
            crawl_product_pipeline, "extract_product_data",
            _make_extract({"name": "变更产品", "company": "变更公司", "type": "医疗险", "premium_min": 600}),
        )
        second = crawl_product_pipeline.execute_crawl_job(db, job)
        assert second.status == "success"
        assert db.query(RawDocument).count() == 2
        assert db.query(ProductDraft).count() == 2
        assert db.query(ProductReviewTask).count() == 2
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 停售检测：关键词、404/内容缺失；批准后停售、回滚恢复
# ---------------------------------------------------------------------------

def test_crawl_off_shelf_keyword_draft_and_approve_deactivates(client, admin_headers, monkeypatch):
    db = SessionLocal()
    try:
        from backend.app.services.product_service import create_product
        existing = create_product(db, {
            "name": "停售检测品", "company": "检测公司", "type": "医疗险",
            "premium_min": 500, "premium_max": 800, "sum_insured_max": 300,
            "rule": {"min_age": 0, "max_age": 60, "job_class_limit": 6, "waiting_period_days": 90},
        })
        existing_id = existing.id
    finally:
        db.close()

    page_url = f"https://example.com/off-shelf-{uuid.uuid4().hex[:8]}"
    _page_id, job_id = _create_page_and_job(client, admin_headers, url=page_url)
    monkeypatch.setattr(crawl_product_pipeline, "fetch_source_page", _make_fetch("本产品已停售，暂不可投保"))
    monkeypatch.setattr(
        crawl_product_pipeline, "extract_product_data",
        _make_extract({"name": "停售检测品", "company": "检测公司", "type": "医疗险", "premium_min": 500}),
    )

    db = SessionLocal()
    try:
        job = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
        run = crawl_product_pipeline.execute_crawl_job(db, job)
        assert run.status == "success"

        draft = db.query(ProductDraft).order_by(ProductDraft.id.desc()).first()
        assert draft.draft_data.get("off_shelf") is True
        assert draft.matched_product_id == existing_id
        task = db.query(ProductReviewTask).filter(ProductReviewTask.product_draft_id == draft.id).first()
        task_id = task.id
        version_count_before = db.query(ProductVersion).count()
    finally:
        db.close()

    approved = client.post(f"/api/admin/ingestion/review-tasks/{task_id}/approve", headers=admin_headers, json={"note": "确认停售"})
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["product_id"] == existing_id

    db = SessionLocal()
    try:
        product = db.query(Product).filter(Product.id == existing_id).first()
        assert product.status == 0, "approved off-shelf draft must deactivate the product"
        version = db.query(ProductVersion).filter(ProductVersion.product_id == existing_id).order_by(ProductVersion.id.desc()).first()
        assert version is not None
        assert version.version_data.get("off_shelf") is True
        assert db.query(ProductVersion).count() == version_count_before + 1
        version_id = version.id
    finally:
        db.close()

    rolled_back = client.post(f"/api/admin/ingestion/versions/{version_id}/rollback", headers=admin_headers)
    assert rolled_back.status_code == 200, rolled_back.text
    db = SessionLocal()
    try:
        product = db.query(Product).filter(Product.id == existing_id).first()
        assert product.status == 1, "rollback must reactivate the product"
    finally:
        db.close()


def test_crawl_404_empty_content_marks_off_shelf_with_identity(client, admin_headers, monkeypatch):
    db = SessionLocal()
    try:
        from backend.app.services.product_service import create_product
        existing = create_product(db, {
            "name": "消失产品", "company": "消失公司", "type": "医疗险",
            "premium_min": 500, "premium_max": 800, "sum_insured_max": 300,
            "rule": {"min_age": 0, "max_age": 60, "job_class_limit": 6, "waiting_period_days": 90},
        })
        existing_id = existing.id
    finally:
        db.close()

    _page_id, job_id = _create_page_and_job(client, admin_headers)

    db = SessionLocal()
    try:
        job = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
        monkeypatch.setattr(crawl_product_pipeline, "fetch_source_page", _make_fetch("消失产品 医疗险 保费500"))
        monkeypatch.setattr(
            crawl_product_pipeline, "extract_product_data",
            _make_extract({"name": "消失产品", "company": "消失公司", "type": "医疗险", "premium_min": 500}),
        )
        first = crawl_product_pipeline.execute_crawl_job(db, job)
        assert first.status == "success"

        monkeypatch.setattr(crawl_product_pipeline, "fetch_source_page", _make_fetch("", http_status=404))
        second = crawl_product_pipeline.execute_crawl_job(db, job)
        assert second.status == "success"
        assert second.http_status == 404

        draft = db.query(ProductDraft).order_by(ProductDraft.id.desc()).first()
        assert draft.draft_data.get("off_shelf") is True
        assert draft.draft_data.get("name") == "消失产品"
        assert draft.draft_data.get("company") == "消失公司"
        assert draft.draft_data.get("type") == "医疗险"
        assert draft.matched_product_id == existing_id
        task = db.query(ProductReviewTask).filter(ProductReviewTask.product_draft_id == draft.id).first()
        task_id = task.id
    finally:
        db.close()

    approved = client.post(f"/api/admin/ingestion/review-tasks/{task_id}/approve", headers=admin_headers, json={"note": "页面404，确认停售"})
    assert approved.status_code == 200, approved.text
    db = SessionLocal()
    try:
        assert db.query(Product).filter(Product.id == existing_id).first().status == 0
    finally:
        db.close()


def test_crawl_fetch_failure_records_failed_run(client, admin_headers, monkeypatch):
    _page_id, job_id = _create_page_and_job(client, admin_headers)

    def broken_fetch(source_page):
        raise RuntimeError("connection refused to source")

    monkeypatch.setattr(crawl_product_pipeline, "fetch_source_page", broken_fetch)

    db = SessionLocal()
    try:
        job = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
        run = crawl_product_pipeline.execute_crawl_job(db, job)
        assert run.status == "failed"
        assert "connection refused" in (run.error_message or "")
        assert run.finished_at is not None
        assert db.query(ProductDraft).count() == 0
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 审核：批准（原子发布）、拒绝（不落库）、回滚
# ---------------------------------------------------------------------------

def _manual_extraction(client, headers, page_id: int, data: dict) -> int:
    response = client.post(
        "/api/admin/ingestion/manual-extractions",
        headers=headers,
        json={"source_page_id": page_id, "text": "人工审核文本", "extracted_data": data, "confidence": 0.9},
    )
    assert response.status_code == 200, response.text
    return response.json()["review_task_id"]


def test_approve_publishes_recommendable_and_provenance(client, admin_headers):
    page_url = f"https://example.com/prov-{uuid.uuid4().hex[:8]}"
    page_id, _job_id = _create_page_and_job(client, admin_headers, url=page_url)
    data = {
        "name": "后台审核产品", "company": "后台公司", "type": "医疗险",
        "premium_min": 500, "premium_max": 800, "sum_insured_min": 100, "sum_insured_max": 300,
        "min_age": 0, "max_age": 60, "job_class_limit": 6, "waiting_period_days": 30,
        "benefits": [{"benefit_type": "basic", "benefit_name": "住院医疗", "benefit_amount": "100万", "payment_limit": "按条款"}],
    }
    task_id = _manual_extraction(client, admin_headers, page_id, data)

    from backend.app.engine.models import UserProfile
    from backend.app.engine.rule_engine import filter_candidate_pool_with_reasons

    db = SessionLocal()
    try:
        user = UserProfile(age=30, gender="male", annual_income=200000, job_class=2, life_stage="single",
                           family_burden="none", health_status="standard")
        candidates_before, _ = filter_candidate_pool_with_reasons(db, user)
        assert not any(p.name == "后台审核产品" for p in candidates_before), "pending draft must not be recommendable"
        product_count_before = db.query(Product).count()
        version_count_before = db.query(ProductVersion).count()
    finally:
        db.close()

    approved = client.post(f"/api/admin/ingestion/review-tasks/{task_id}/approve", headers=admin_headers, json={"note": "ok"})
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["status"] == "approved"
    assert body["product_id"] is not None
    assert body["version_id"] is not None

    db = SessionLocal()
    try:
        assert db.query(Product).count() == product_count_before + 1
        assert db.query(ProductVersion).count() == version_count_before + 1
        product = db.query(Product).filter(Product.id == body["product_id"]).first()
        assert product.status == 1
        assert product.premium_min == 500
        rule = db.query(Rule).filter(Rule.product_id == product.id).first()
        assert rule is not None and rule.waiting_period_days == 30
        assert db.query(Benefit).filter(Benefit.product_id == product.id).count() == 1

        candidates_after, _ = filter_candidate_pool_with_reasons(db, user)
        assert any(p.id == product.id for p in candidates_after), "approved product must be recommendable"
        product_id = product.id
    finally:
        db.close()

    provenance = client.get(f"/api/admin/ingestion/products/{product_id}/provenance", headers=admin_headers)
    assert provenance.status_code == 200, provenance.text
    prov = provenance.json()
    assert prov["name"] == "后台审核产品"
    assert prov["last_verified_at"] is not None
    assert any(p["url"] == page_url and p["last_crawled_at"] is not None for p in prov["source_pages"])
    assert len(prov["versions"]) == 1
    assert prov["versions"][0]["name"] == "后台审核产品"

    versions = client.get("/api/admin/ingestion/versions", headers=admin_headers)
    assert versions.status_code == 200, versions.text
    assert any(v["id"] == body["version_id"] for v in versions.json()["versions"])


def test_reject_does_not_write_catalog(client, admin_headers):
    page_id, _job_id = _create_page_and_job(client, admin_headers)
    task_id = _manual_extraction(client, admin_headers, page_id, {
        "name": "被拒产品", "company": "被拒公司", "type": "医疗险", "premium_min": 500,
    })

    db = SessionLocal()
    try:
        product_count_before = db.query(Product).count()
        version_count_before = db.query(ProductVersion).count()
    finally:
        db.close()

    rejected = client.post(f"/api/admin/ingestion/review-tasks/{task_id}/reject", headers=admin_headers, json={"note": "数据不可信"})
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"

    db = SessionLocal()
    try:
        assert db.query(Product).count() == product_count_before, "rejected draft must not create products"
        assert db.query(ProductVersion).count() == version_count_before
        task = db.query(ProductReviewTask).filter(ProductReviewTask.id == task_id).first()
        assert task.status == "rejected"
        assert task.review_note == "数据不可信"
        draft = db.query(ProductDraft).filter(ProductDraft.id == task.product_draft_id).first()
        assert draft.status == "rejected"
        product_id = None
    finally:
        db.close()

    provenance = client.get("/api/admin/ingestion/products/1/provenance", headers=admin_headers)
    assert provenance.status_code == 404


def test_approve_updates_matched_existing_product(client, admin_headers):
    created = client.post("/api/products", headers=admin_headers, json={
        "name": "已存在医疗产品", "company": "已存在公司", "type": "医疗险",
        "premium_min": 500, "premium_max": 800, "sum_insured_max": 300,
        "rule": {"min_age": 0, "max_age": 60, "job_class_limit": 6, "waiting_period_days": 30},
    })
    assert created.status_code == 201, created.text
    existing_id = created.json()["id"]

    page_id, _job_id = _create_page_and_job(client, admin_headers)
    task_id = _manual_extraction(client, admin_headers, page_id, {
        "name": "已存在医疗产品", "company": "已存在公司", "type": "医疗险",
        "premium_min": 800, "premium_max": 1000, "waiting_period_days": 60,
    })

    db = SessionLocal()
    try:
        draft = db.query(ProductDraft).order_by(ProductDraft.id.desc()).first()
        assert draft.matched_product_id == existing_id, "draft must be matched to the existing product"
    finally:
        db.close()

    approved = client.post(f"/api/admin/ingestion/review-tasks/{task_id}/approve", headers=admin_headers, json={"note": "价格更新"})
    assert approved.status_code == 200, approved.text
    assert approved.json()["product_id"] == existing_id

    db = SessionLocal()
    try:
        assert db.query(Product).count() == 1, "approval of a matched draft must update, not duplicate"
        product = db.query(Product).filter(Product.id == existing_id).first()
        assert product.premium_min == 800
        rule = db.query(Rule).filter(Rule.product_id == existing_id).first()
        assert rule.waiting_period_days == 60
    finally:
        db.close()


def test_approve_off_shelf_draft_without_match_fails(client, admin_headers):
    page_id, _job_id = _create_page_and_job(client, admin_headers)
    task_id = _manual_extraction(client, admin_headers, page_id, {
        "name": "孤儿停售品", "company": "未知公司", "type": "医疗险", "off_shelf": True,
    })

    db = SessionLocal()
    try:
        draft = db.query(ProductDraft).order_by(ProductDraft.id.desc()).first()
        assert draft.matched_product_id is None
        product_count_before = db.query(Product).count()
    finally:
        db.close()

    response = client.post(f"/api/admin/ingestion/review-tasks/{task_id}/approve", headers=admin_headers, json={"note": "停售"})
    assert response.status_code == 400, response.text
    assert "off_shelf" in response.json()["detail"]

    db = SessionLocal()
    try:
        assert db.query(Product).count() == product_count_before
        assert db.query(ProductVersion).count() == 0
    finally:
        db.close()


def test_rollback_restores_published_snapshot(client, admin_headers):
    page_id, _job_id = _create_page_and_job(client, admin_headers)
    task_id = _manual_extraction(client, admin_headers, page_id, {
        "name": "回滚产品", "company": "回滚公司", "type": "医疗险",
        "premium_min": 500, "premium_max": 800, "sum_insured_max": 300,
        "min_age": 0, "max_age": 60, "job_class_limit": 6, "waiting_period_days": 90,
    })
    approved = client.post(f"/api/admin/ingestion/review-tasks/{task_id}/approve", headers=admin_headers, json={"note": "发布"})
    assert approved.status_code == 200, approved.text
    product_id = approved.json()["product_id"]
    version_id = approved.json()["version_id"]

    updated = client.put(f"/api/products/{product_id}", headers=admin_headers, json={"premium_min": 9999, "rule": {"min_age": 18}})
    assert updated.status_code == 200, updated.text

    rolled_back = client.post(f"/api/admin/ingestion/versions/{version_id}/rollback", headers=admin_headers)
    assert rolled_back.status_code == 200, rolled_back.text

    db = SessionLocal()
    try:
        product = db.query(Product).filter(Product.id == product_id).first()
        assert product.premium_min == 500, "rollback must restore the published snapshot"
        rule = db.query(Rule).filter(Rule.product_id == product_id).first()
        assert rule.min_age == 0
        assert rule.waiting_period_days == 90
    finally:
        db.close()


def test_approve_is_atomic_single_transaction(client, admin_headers, monkeypatch):
    """Publish commits exactly once; a mid-transaction failure leaves no rows."""
    from backend.app.data_ingestion.review import approve_review_task
    from backend.app.services import product_service

    page_id, _job_id = _create_page_and_job(client, admin_headers)
    task_id = _manual_extraction(client, admin_headers, page_id, {
        "name": "原子产品", "company": "原子公司", "type": "医疗险",
        "premium_min": 500, "min_age": 0, "max_age": 60,
        "benefits": [{"benefit_type": "basic", "benefit_name": "住院医疗", "benefit_amount": "100万"}],
    })

    db = SessionLocal()
    try:
        task = db.query(ProductReviewTask).filter(ProductReviewTask.id == task_id).first()

        original_commit = db.commit
        commits: list[int] = []

        def counting_commit():
            commits.append(1)
            original_commit()

        db.commit = counting_commit
        try:
            approve_review_task(db, task, 1, "ok")
        finally:
            db.commit = original_commit
        assert len(commits) == 1, "product + rule + benefit + version must publish in a single transaction"
        assert db.query(Product).count() == 1
        assert db.query(ProductVersion).count() == 1

        db.query(Product).delete()
        db.query(ProductVersion).delete()
        db.query(Rule).delete()
        db.query(Benefit).delete()
        draft = db.query(ProductDraft).filter(ProductDraft.id == task.product_draft_id).first()
        draft.status = "pending_review"
        db.commit()

        def failing_update(db_session, product_id, data, commit=True):
            db_session.flush()
            raise RuntimeError("simulated mid-write failure")

        monkeypatch.setattr(product_service, "update_product", failing_update)
        with pytest.raises(RuntimeError):
            approve_review_task(db, task, 1, "ok")
        db.rollback()
        assert db.query(Product).count() == 0, "failed publish must not leave a product row"
        assert db.query(ProductVersion).count() == 0, "failed publish must not leave a version row"
        assert db.query(ProductDraft).filter(ProductDraft.id == task.product_draft_id).first().status == "pending_review"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 可观测性：/api/admin/logs 返回真实日志
# ---------------------------------------------------------------------------

def test_admin_logs_endpoint_returns_real_logs(client, admin_headers, monkeypatch):
    logs_before = client.get("/api/admin/logs", headers=admin_headers)
    assert logs_before.status_code == 200, logs_before.text
    assert isinstance(logs_before.json()["logs"], list)
    assert isinstance(logs_before.json()["crawl_runs"], list)

    page_id, job_id = _create_page_and_job(client, admin_headers)
    task_id = _manual_extraction(client, admin_headers, page_id, {
        "name": "日志产品", "company": "日志公司", "type": "医疗险", "premium_min": 500,
    })
    client.post(f"/api/admin/ingestion/review-tasks/{task_id}/approve", headers=admin_headers, json={"note": "ok"})

    def fake_execute(db, crawl_job):
        run = CrawlRun(crawl_job_id=crawl_job.id, status="success", http_status=200)
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    monkeypatch.setattr(scheduler_module, "execute_crawl_job", fake_execute)
    client.post(f"/api/admin/ingestion/jobs/{job_id}/run", headers=admin_headers)
    db = SessionLocal()
    try:
        assert _wait_for_run(db, job_id) is not None
    finally:
        db.close()

    logs_after = client.get("/api/admin/logs", headers=admin_headers)
    assert logs_after.status_code == 200, logs_after.text
    body = logs_after.json()
    actions = [log["action"] for log in body["logs"]]
    assert "ingestion.extraction.review_created" in actions
    assert "ingestion.review.approve" in actions
    assert "ingestion.job.run" in actions
    assert any(run["crawl_job_id"] == job_id and run["status"] == "success" for run in body["crawl_runs"])
