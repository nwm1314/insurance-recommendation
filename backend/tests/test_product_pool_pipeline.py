"""TASK-034 回归：聚合站产品池发现、高置信自动发布、seed 门控与来源类型。

策略基线：聚合站（慧择/开心保）为产品主数据源，官网作补充验证；
未经审核或未达自动发布门槛的草稿不得影响推荐（TASK-018 安全边界）。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(tempfile.gettempdir(), 'insurance_product_pool_pytest.db').replace(os.sep, '/')}",
)
os.environ.setdefault("DISABLE_SCHEDULER_IN_TESTS", "true")

try:
    os.remove(os.path.join(tempfile.gettempdir(), "insurance_product_pool_pytest.db"))
except OSError:
    pass

import pytest

from backend.app.database import SessionLocal, init_db

init_db()

from backend.app.config import settings
from backend.app.data_ingestion import discovery as discovery_module
from backend.app.data_ingestion.auto_publish import evaluate_auto_publish
from backend.app.data_ingestion.discovery import extract_detail_urls
from backend.app.data_ingestion.fetchers.page_fetcher import FetchResult, RobotsBlockedError
from backend.app.data_ingestion.pipeline import (
    create_extraction_review,
    create_source_page,
    ensure_seed_products_if_empty,
    ensure_seed_sources,
)
from backend.app.models.auth import AuditLog
from backend.app.models.data_ingestion import (
    CrawlJob,
    ProductDraft,
    ProductReviewTask,
    ProductVersion,
    SourcePage,
    SourcePlatform,
)
from backend.app.models.product import Product


@pytest.fixture(autouse=True)
def _clean_db(monkeypatch):
    """每个用例独占干净的产品池表：本文件的用例互不共享目录/草稿状态。"""
    monkeypatch.setattr(settings, "auto_publish_enabled", True)
    monkeypatch.setattr(settings, "auto_publish_confidence", 0.8)
    monkeypatch.setattr(settings, "seed_demo_products", False)
    monkeypatch.setattr(settings, "discovery_enabled", True)
    monkeypatch.setattr(settings, "discovery_max_new_per_source", 20)
    db = SessionLocal()
    try:
        for model in (
            ProductVersion, ProductReviewTask, ProductDraft,
        ):
            db.query(model).delete()
        from backend.app.models.data_ingestion import CrawlRun, ExtractionRun, ProductFieldEvidence, RawDocument
        from backend.app.models.benefit import Benefit
        from backend.app.models.rule import Rule

        for model in (
            ProductFieldEvidence, ExtractionRun, RawDocument, CrawlRun, CrawlJob,
            SourcePage, Product, Rule, Benefit, AuditLog,
        ):
            db.query(model).delete()
        db.commit()
    finally:
        db.close()
    yield


def _platform(db: SessionLocal, name: str = "慧择网") -> SourcePlatform:
    platform = db.query(SourcePlatform).filter(SourcePlatform.name == name).first()
    if platform is None:
        platform = SourcePlatform(name=name, platform_type="third_party", base_url="https://example.com", robots_url="https://example.com/robots.txt")
        db.add(platform)
        db.commit()
        db.refresh(platform)
    return platform


def _raw_document(db, url: str = "https://www.huize.com/apps/cps/index/product/detail?prodId=1"):
    from backend.app.data_ingestion.pipeline import archive_raw_document

    platform = _platform(db)
    page = create_source_page(db, platform.id, url)
    return archive_raw_document(db, page, "page text", "<html></html>")


def _draft_data(**overrides) -> dict:
    data = {
        "name": "真实产品A款",
        "company": "中国平安",
        "type": "医疗险",
        "premium_min": 300,
        "premium_max": 600,
        "sum_insured_min": 200,
        "sum_insured_max": 400,
        "coverage_period": "1年",
        "payment_period": "1年",
        "source_url": "https://www.huize.com/apps/cps/index/product/detail?prodId=1",
    }
    data.update(overrides)
    return data


# ------------------------------------------------------------ discovery

def test_extract_detail_urls_matches_only_product_patterns():
    html = """
    <a href="https://www.huize.com/apps/cps/index/product/detail?prodId=104104&amp;planId=108706">产品</a>
    <a href="//www.huize.com/apps/cps/index/product/detail?prodId=104290">相对协议</a>
    <a href="https://www.huize.com/apps/cps/index/product/detail?prodId=104104">重复去抖</a>
    <a href="https://www.huize.com/hz-planet/gonglue/1">攻略不匹配</a>
    <a href="javascript:void(0)">忽略</a>
    """
    urls = extract_detail_urls(html, "https://www.huize.com/", discovery_module.DISCOVERY_SOURCES[0]["detail_pattern"])
    assert len(urls) == 2
    assert "https://www.huize.com/apps/cps/index/product/detail?prodId=104104" in urls
    assert "https://www.huize.com/apps/cps/index/product/detail?prodId=104290" in urls


def test_extract_detail_urls_kaixinbao_strips_tracking_query():
    html = '<a href="/jiankang-baoxian/123.shtml?utm_campaign=x%20y">健康险</a>'
    urls = extract_detail_urls(html, "https://www.kaixinbao.com/", discovery_module.DISCOVERY_SOURCES[1]["detail_pattern"])
    assert urls == ["https://www.kaixinbao.com/jiankang-baoxian/123.shtml"]


def test_discovery_registers_pages_and_jobs_idempotently(monkeypatch):
    db = SessionLocal()
    try:
        platform = _platform(db)
        html = (
            '<a href="https://www.huize.com/apps/cps/index/product/detail?prodId=1">A</a>'
            '<a href="https://www.huize.com/apps/cps/index/product/detail?prodId=2">B</a>'
        )
        monkeypatch.setattr(discovery_module, "fetch_source_page", lambda page: FetchResult(text="t", html=html, http_status=200))
        source = {"platform_name": "慧择网", "entries": ["https://www.huize.com/"], "detail_pattern": discovery_module.DISCOVERY_SOURCES[0]["detail_pattern"]}
        result = discovery_module.discover_products_for_platform(db, source)
        assert result["created"] == 2
        assert db.query(SourcePage).filter(SourcePage.page_type == "product").count() == 2
        assert db.query(CrawlJob).count() == 2

        # 再跑一次：全部已存在，不新建
        result2 = discovery_module.discover_products_for_platform(db, source)
        assert result2["created"] == 0
        assert result2["skipped_existing"] == 2
        assert db.query(CrawlJob).count() == 2
    finally:
        db.close()


def test_discovery_respects_robots_block(monkeypatch):
    db = SessionLocal()
    try:
        _platform(db)

        def blocked(page):
            raise RobotsBlockedError("robots.txt disallows fetching")

        monkeypatch.setattr(discovery_module, "fetch_source_page", blocked)
        source = {"platform_name": "慧择网", "entries": ["https://www.huize.com/"], "detail_pattern": r"."}
        result = discovery_module.discover_products_for_platform(db, source)
        assert result["created"] == 0
        assert result["errors"]
        # robots 拒绝时也不得登记任何产品页
        assert db.query(SourcePage).filter(SourcePage.page_type == "product").count() == 0
    finally:
        db.close()


def test_seed_sources_deactivates_zhongmin_and_adds_shenlanbao():
    db = SessionLocal()
    try:
        db.add(SourcePlatform(name="中民保险网", platform_type="third_party", base_url="https://www.zhongmin.cn"))
        db.commit()
        ensure_seed_sources(db)
        zhongmin = db.query(SourcePlatform).filter(SourcePlatform.name == "中民保险网").first()
        assert zhongmin.is_active is False
        shenlan = db.query(SourcePlatform).filter(SourcePlatform.name == "深蓝保").first()
        assert shenlan is not None and shenlan.rate_limit_seconds == 15
        kaixin = db.query(SourcePlatform).filter(SourcePlatform.name == "开心保").first()
        assert kaixin.rate_limit_seconds == 10
    finally:
        db.close()


# ------------------------------------------------------------ auto-publish

def test_auto_publish_publishes_high_confidence_llm_draft():
    db = SessionLocal()
    try:
        raw = _raw_document(db)
        task = create_extraction_review(db, raw, _draft_data(), confidence=0.85, extractor="llm")
        db.refresh(task)
        assert task.status == "approved"
        draft = db.query(ProductDraft).filter(ProductDraft.id == task.product_draft_id).first()
        assert draft.status == "published"
        product = db.query(Product).filter(Product.name == "真实产品A款").first()
        assert product is not None and product.status == 1
        version = db.query(ProductVersion).filter(ProductVersion.product_draft_id == draft.id).first()
        assert version is not None and version.published_by is None
        audit = db.query(AuditLog).filter(AuditLog.action == "review.auto_publish").first()
        assert audit is not None and audit.detail["product_id"] == product.id
    finally:
        db.close()


def test_auto_publish_skips_low_confidence_and_non_llm():
    db = SessionLocal()
    try:
        raw = _raw_document(db)
        task = create_extraction_review(db, raw, _draft_data(), confidence=0.6, extractor="llm")
        assert task.status == "pending"

        raw2 = _raw_document(db, "https://www.huize.com/apps/cps/index/product/detail?prodId=2")
        task2 = create_extraction_review(db, raw2, _draft_data(name="启发式产品"), confidence=0.9, extractor="heuristic")
        assert task2.status == "pending"
        drafts = db.query(ProductDraft).filter(ProductDraft.status == "pending_review").count()
        assert drafts == 2
    finally:
        db.close()


def test_auto_publish_blocked_by_placeholders_and_missing_fields():
    db = SessionLocal()
    try:
        cases = [
            _draft_data(name="待审核产品"),
            _draft_data(company="待审核"),
            _draft_data(premium_min=0),
            _draft_data(sum_insured_max=0),
            _draft_data(source_url=None),
        ]
        drafts = []
        for i, data in enumerate(cases, start=10):
            raw = _raw_document(db, f"https://www.huize.com/apps/cps/index/product/detail?prodId={i}")
            task = create_extraction_review(db, raw, data, confidence=0.9, extractor="llm")
            assert task.status == "pending", f"case {i} must stay pending"
            drafts.append(task.product_draft_id)
        assert db.query(Product).filter(Product.status == 1).count() == 0
    finally:
        db.close()


def test_auto_publish_off_shelf_only_with_exact_match():
    db = SessionLocal()
    try:
        # 先发布一个真实产品
        raw = _raw_document(db)
        task = create_extraction_review(db, raw, _draft_data(), confidence=0.85, extractor="llm")
        assert task.status == "approved"
        product = db.query(Product).filter(Product.name == "真实产品A款").first()

        # 精确匹配的停售草稿 → 自动发布停售
        raw2 = _raw_document(db, "https://www.huize.com/apps/cps/index/product/detail?prodId=11")
        off_shelf = _draft_data(off_shelf=True)
        # match_product_for_draft 精确匹配 name+company → matched_product_id
        task2 = create_extraction_review(db, raw2, off_shelf, confidence=1.0, extractor="off_shelf_detector")
        assert task2.status == "approved"
        db.refresh(product)
        assert product.status == 0

        # 再次发布（非停售）→ 必须重新上架，否则真实数据永远进不了推荐池
        raw3 = _raw_document(db, "https://www.huize.com/apps/cps/index/product/detail?prodId=12")
        task3 = create_extraction_review(db, raw3, _draft_data(), confidence=0.85, extractor="llm")
        assert task3.status == "approved"
        db.refresh(product)
        assert product.status == 1

        # 无匹配的停售草稿 → 人工审核
        raw4 = _raw_document(db, "https://www.huize.com/apps/cps/index/product/detail?prodId=13")
        task4 = create_extraction_review(db, raw4, {"off_shelf": True, "name": "完全未知产品", "company": "某公司"}, confidence=1.0, extractor="off_shelf_detector")
        assert task4.status == "pending"
    finally:
        db.close()


def test_auto_publish_fuzzy_match_needs_review():
    """模糊匹配（如 达尔文7号 vs 达尔文8号）不得自动覆盖既有产品。"""
    db = SessionLocal()
    try:
        raw = _raw_document(db)
        task = create_extraction_review(db, raw, _draft_data(), confidence=0.85, extractor="llm")
        assert task.status == "approved"

        # 同险种名称相似但非精确 → pipeline 模糊匹配上，但自动发布必须拒绝
        raw2 = _raw_document(db, "https://www.huize.com/apps/cps/index/product/detail?prodId=13")
        task2 = create_extraction_review(db, raw2, _draft_data(name="真实产品A款Pro"), confidence=0.9, extractor="llm")
        assert task2.status == "pending"
        draft2 = db.query(ProductDraft).filter(ProductDraft.id == task2.product_draft_id).first()
        should, reason = evaluate_auto_publish(draft2, "llm")
        assert should is False
        assert reason == "fuzzy_match_needs_review"
    finally:
        db.close()


def test_auto_publish_disabled_by_settings(monkeypatch):
    db = SessionLocal()
    try:
        monkeypatch.setattr(settings, "auto_publish_enabled", False)
        raw = _raw_document(db, "https://www.huize.com/apps/cps/index/product/detail?prodId=14")
        task = create_extraction_review(db, raw, _draft_data(name="禁用自动发布产品"), confidence=0.9, extractor="llm")
        assert task.status == "pending"
    finally:
        db.close()


# ------------------------------------------------------------ seed gating

def test_seed_demo_products_gated_by_settings(monkeypatch):
    db = SessionLocal()
    try:
        monkeypatch.setattr(settings, "seed_demo_products", False)
        ensure_seed_products_if_empty(db)
        assert db.query(Product).count() == 0

        called = []
        monkeypatch.setattr(settings, "seed_demo_products", True)
        import backend.app.data_ingestion.pipeline as pipeline_module
        monkeypatch.setattr("backend.scripts.seed.seed", lambda: called.append(True))
        ensure_seed_products_if_empty(db)
        assert called, "SEED_DEMO_PRODUCTS=true 且库为空时应执行 seed"
    finally:
        db.close()


# ------------------------------------------------------------ source type

def test_source_type_official_vs_aggregator():
    from backend.app.api.recommend import _source_type

    class P:
        source_url = "https://life.pingan.com/"
        company = "平安人寿"

    class A:
        source_url = "https://www.huize.com/apps/cps/index/product/detail?prodId=1"
        company = "中国平安"

    class N:
        source_url = None
        company = "中国平安"

    assert _source_type(P()) == "official"
    assert _source_type(A()) == "aggregator"
    assert _source_type(N()) == ""
