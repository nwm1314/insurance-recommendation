import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(tempfile.gettempdir(), 'insurance_stage3_pytest.db').replace(os.sep, '/')}",
)
os.environ.setdefault("DISABLE_SCHEDULER_IN_TESTS", "true")

try:
    os.remove(os.path.join(tempfile.gettempdir(), "insurance_stage3_pytest.db"))
except OSError:
    pass

import pytest
from fastapi.testclient import TestClient

import backend.app.api.ingestion as ingestion_api
import backend.app.crawler.scheduler as scheduler_module
import backend.app.data_ingestion.pipelines.crawl_product as crawl_product_pipeline
from backend.main import app
from backend.app.database import SessionLocal
from backend.app.models.auth import AuditLog, RecommendationRecord, RefreshToken, SavedProfile, User, UserRole
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


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clean_data():
    _clean_auth_data()
    _clean_ingestion_data()
    yield
    _clean_ingestion_data()
    _clean_auth_data()


def _clean_auth_data():
    db = SessionLocal()
    try:
        db.query(AuditLog).delete()
        db.query(RecommendationRecord).delete()
        db.query(SavedProfile).delete()
        db.query(RefreshToken).delete()
        db.query(UserRole).delete()
        db.query(User).delete()
        db.commit()
    finally:
        db.close()


def _clean_ingestion_data():
    db = SessionLocal()
    try:
        db.query(ProductFieldEvidence).delete()
        db.query(ProductReviewTask).delete()
        db.query(ProductVersion).delete()
        db.query(ProductDraft).delete()
        db.query(ExtractionRun).delete()
        db.query(CrawlRun).delete()
        db.query(RawDocument).delete()
        db.query(CrawlJob).delete()
        db.query(SourcePage).delete()
        db.commit()
    finally:
        db.close()


def _register(client: TestClient, email: str, password: str = "Password12345") -> dict:
    response = client.post("/api/auth/register", json={"email": email, "password": password, "full_name": email})
    assert response.status_code == 200, response.text
    return response.json()


def test_auth_register_login_refresh_me_logout(client):
    registered = _register(client, "admin-auth-test@example.com")
    assert "admin" not in registered["roles"]
    assert "user" in registered["roles"]
    assert "product:write" not in registered["permissions"]

    login = client.post("/api/auth/login", json={"email": "admin-auth-test@example.com", "password": "Password12345"})
    assert login.status_code == 200, login.text

    access_token = client.cookies.get("access_token")
    assert access_token is not None
    headers = {"Authorization": f"Bearer {access_token}"}
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    assert me.json()["email"] == "admin-auth-test@example.com"

    refreshed = client.post("/api/auth/refresh")
    assert refreshed.status_code == 200, refreshed.text

    logout = client.post("/api/auth/logout", headers=headers)
    assert logout.status_code == 200, logout.text


def test_admin_ingestion_permissions_and_core_flow(client, monkeypatch):
    db = SessionLocal()
    try:
        from backend.app.config import settings as app_settings
        from backend.app.services.auth_service import ensure_auth_defaults

        monkeypatch.setattr(app_settings, "first_admin_email", "admin-ingestion-test@example.com")
        monkeypatch.setattr(app_settings, "first_admin_password", "Password12345")
        ensure_auth_defaults(db)
    finally:
        db.close()
    user = _register(client, "normal-ingestion-test@example.com")
    # Login as admin to get cookie-based token
    admin_login = client.post("/api/auth/login", json={"email": "admin-ingestion-test@example.com", "password": "Password12345"})
    assert admin_login.status_code == 200, admin_login.text
    admin_token = client.cookies.get("access_token")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    # Login as normal user
    user_login = client.post("/api/auth/login", json={"email": "normal-ingestion-test@example.com", "password": "Password12345"})
    assert user_login.status_code == 200, user_login.text
    user_token = client.cookies.get("access_token")
    user_headers = {"Authorization": f"Bearer {user_token}"}

    # Clear cookies to test unauthenticated access
    client.cookies.clear()
    assert client.get("/api/admin/ingestion/status").status_code == 401
    assert client.get("/api/admin/ingestion/status", headers=user_headers).status_code == 403
    assert client.get("/api/admin/ingestion/status", headers=admin_headers).status_code == 200

    platforms = client.get("/api/admin/ingestion/platforms", headers=admin_headers)
    assert platforms.status_code == 200, platforms.text
    platform_id = platforms.json()["platforms"][0]["id"]

    page = client.post(
        "/api/admin/ingestion/source-pages",
        headers=admin_headers,
        json={"platform_id": platform_id, "url": "https://example.com/pytest-ingestion", "page_type": "product"},
    )
    assert page.status_code == 200, page.text
    page_id = page.json()["id"]

    job = client.post(
        "/api/admin/ingestion/jobs",
        headers=admin_headers,
        json={"name": "pytest ingestion job", "source_page_id": page_id},
    )
    assert job.status_code == 200, job.text
    job_id = job.json()["id"]

    def fake_execute(db, crawl_job):
        run = CrawlRun(crawl_job_id=crawl_job.id, status="success", http_status=200)
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    monkeypatch.setattr(scheduler_module, "execute_crawl_job", fake_execute)
    triggered = client.post(f"/api/admin/ingestion/jobs/{job_id}/run", headers=admin_headers)
    assert triggered.status_code == 200, triggered.text
    assert triggered.json()["status"] == "started"

    deadline = time.monotonic() + 5
    run = None
    while time.monotonic() < deadline:
        run = (
            db.query(CrawlRun)
            .filter(CrawlRun.crawl_job_id == job_id)
            .order_by(CrawlRun.id.desc())
            .first()
        )
        if run is not None and run.status in ("success", "failed", "skipped"):
            break
        time.sleep(0.02)
    assert run is not None, "background crawl run did not finish in time"
    assert run.status == "success"

    extraction = client.post(
        "/api/admin/ingestion/manual-extractions",
        headers=admin_headers,
        json={
            "source_page_id": page_id,
            "text": "pytest product text",
            "extracted_data": {"name": "Pytest Product", "company": "Pytest Co", "type": "医疗险"},
            "confidence": 0.8,
        },
    )
    assert extraction.status_code == 200, extraction.text
    task_id = extraction.json()["review_task_id"]

    detail = client.get(f"/api/admin/ingestion/review-tasks/{task_id}", headers=admin_headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["draft"]["name"] == "Pytest Product"

    approved = client.post(f"/api/admin/ingestion/review-tasks/{task_id}/approve", headers=admin_headers, json={"note": "ok"})
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"


def test_execute_crawl_job_pipeline_without_network(monkeypatch):
    from backend.app.data_ingestion.fetchers.page_fetcher import FetchResult
    from backend.app.data_ingestion.pipelines.crawl_product import execute_crawl_job

    db = SessionLocal()
    try:
        platform = db.query(SourcePlatform).filter(SourcePlatform.name == "NoNetwork").first()
        if platform is None:
            platform = SourcePlatform(name="NoNetwork", platform_type="official", base_url="https://example.com", rate_limit_seconds=0)
            db.add(platform)
            db.flush()
        page = SourcePage(platform_id=platform.id, url="https://example.com/no-network-product", page_type="product")
        db.add(page)
        db.flush()
        job = CrawlJob(name="no network job", source_page_id=page.id)
        db.add(job)
        db.commit()
        db.refresh(job)

        def fake_fetch(source_page):
            assert source_page.url == page.url
            return FetchResult(
                text="无触网产品文本 医疗险 保费500元 保额300万",
                html="<html>无触网产品文本</html>",
                http_status=200,
            )

        def fake_extract(text, html, url):
            assert "无触网产品文本" in text
            return {
                "name": "无触网医疗险",
                "company": "测试保险",
                "type": "医疗险",
                "premium_min": 500,
                "premium_max": 800,
                "sum_insured_max": 300,
                "waiting_period_days": 30,
            }, 0.91, "pytest_fake"

        monkeypatch.setattr(crawl_product_pipeline, "fetch_source_page", fake_fetch)
        monkeypatch.setattr(crawl_product_pipeline, "extract_product_data", fake_extract)

        run = execute_crawl_job(db, job)

        assert run.status == "success"
        assert run.http_status == 200
        assert run.raw_document_id is not None
        assert db.query(RawDocument).count() == 1
        assert db.query(ExtractionRun).count() == 1
        assert db.query(ProductDraft).count() == 1
        assert db.query(ProductReviewTask).count() == 1
        assert db.query(ProductFieldEvidence).count() >= 7
        draft = db.query(ProductDraft).first()
        assert draft.draft_data["name"] == "无触网医疗险"
    finally:
        db.close()
