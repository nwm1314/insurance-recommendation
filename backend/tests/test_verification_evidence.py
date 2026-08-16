"""TASK-035 回归：官网交叉验证（L2）、双聚合站交叉印证、深蓝保测评佐证。

策略基线（用户确认）：L2 存在性 + 双源交叉；验证结果仅标注（不影响在售/
推荐/自动发布）；结果页徽标展示；深蓝保链接级佐证（不复制正文）。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(tempfile.gettempdir(), 'insurance_verification_pytest.db').replace(os.sep, '/')}",
)
os.environ.setdefault("DISABLE_SCHEDULER_IN_TESTS", "true")

try:
    os.remove(os.path.join(tempfile.gettempdir(), "insurance_verification_pytest.db"))
except OSError:
    pass

import pytest

from backend.app.database import SessionLocal, init_db

init_db()

from backend.app.config import settings
from backend.app.data_ingestion import official_verification as ov
from backend.app.data_ingestion import review_evidence as re_ev
from backend.app.data_ingestion.fetchers.page_fetcher import FetchResult
from backend.app.data_ingestion.pipeline import (
    archive_raw_document,
    create_extraction_review,
    create_source_page,
    ensure_seed_sources,
)
from backend.app.models.auth import AuditLog
from backend.app.models.data_ingestion import (
    CrawlRun,
    CrawlJob,
    ExtractionRun,
    ProductDraft,
    ProductReviewTask,
    ProductVersion,
    ProductFieldEvidence,
    RawDocument,
    SourcePage,
    SourcePlatform,
)
from backend.app.models.benefit import Benefit
from backend.app.models.rule import Rule
from backend.app.models.product import Product


@pytest.fixture(autouse=True)
def _clean_db(monkeypatch):
    monkeypatch.setattr(settings, "auto_publish_enabled", True)
    monkeypatch.setattr(settings, "auto_publish_confidence", 0.8)
    monkeypatch.setattr(settings, "seed_demo_products", False)
    monkeypatch.setattr(settings, "official_verification_enabled", True)
    db = SessionLocal()
    try:
        for model in (ProductVersion, ProductReviewTask, ProductDraft):
            db.query(model).delete()
        for model in (
            ProductFieldEvidence, ExtractionRun, RawDocument, CrawlRun, CrawlJob,
            SourcePage, Product, Rule, Benefit, AuditLog,
        ):
            db.query(model).delete()
        db.query(SourcePlatform).filter(SourcePlatform.name.notin_(["慧择网", "开心保"])).delete()
        db.commit()
    finally:
        db.close()
    yield


def _draft_data(name="泰康全能保2026", company="泰康在线", type_="意外险", url="https://www.huize.com/apps/cps/index/product/detail?prodId=1"):
    return {
        "name": name, "company": company, "type": type_,
        "premium_min": 200, "premium_max": 400,
        "sum_insured_min": 10, "sum_insured_max": 100,
        "coverage_period": "1年", "payment_period": "1年",
        "source_url": url,
    }


# ------------------------------------------------------------ 官网 L2 验证

def test_official_names_match_bidirectionally():
    names = ov._extract_official_names("泰康在线财产保险 全能保 综合意外险(全家版) 责任内600万保")
    assert ov._name_matches("泰康全能保2026", names) is True     # 产品名 ⊃ 官网名
    assert ov._name_matches("全能保", names) is True
    assert ov._name_matches("完全无关产品", names) is False


def test_verify_product_official_verified_and_not_found(monkeypatch):
    db = SessionLocal()
    try:
        ensure_seed_sources(db)  # 注册泰康在线官网平台
        product = Product(name="泰康全能保2026", company="泰康在线", type="意外险", status=1,
                          premium_min=200, premium_max=400, sum_insured_max=100)
        db.add(product)
        db.commit()

        monkeypatch.setattr(
            ov, "fetch_source_page",
            # 官网目录为短名形态（如「全能保」），聚合站产品名是其超集
            lambda page: FetchResult(text="泰康在线 全能保 综合意外险(全家版) 责任内600万保额", html=None, http_status=200),
        )
        status = ov.verify_product_official(db, product)
        assert status == ov.VERIFIED
        assert product.official_verification_url == "https://www.tk.cn/product/"
        assert product.official_verified_at is not None

        product2 = Product(name="泰康不存在的产品", company="泰康在线", type="意外险", status=1,
                           premium_min=100, premium_max=200, sum_insured_max=50)
        db.add(product2)
        db.commit()
        assert ov.verify_product_official(db, product2) == ov.NOT_FOUND
    finally:
        db.close()


def test_verify_product_official_unverifiable_company():
    db = SessionLocal()
    try:
        product = Product(name="某产品", company="人保财险", type="意外险", status=1,
                          premium_min=100, premium_max=200, sum_insured_max=50)
        db.add(product)
        db.commit()
        assert ov.verify_product_official(db, product) == ov.UNVERIFIABLE
    finally:
        db.close()


def test_run_official_verifications_respects_batch_and_toggle(monkeypatch):
    db = SessionLocal()
    try:
        for i in range(3):
            db.add(Product(name=f"产品{i}", company="人保财险", type="意外险", status=1,
                           premium_min=100, premium_max=200, sum_insured_max=50))
        db.commit()
        result = ov.run_official_verifications(db, batch=2)
        assert result["checked"] == 2 and result[ov.UNVERIFIABLE] == 2

        monkeypatch.setattr(settings, "official_verification_enabled", False)
        assert ov.run_official_verifications(db)["skipped"] == "disabled"
    finally:
        db.close()


# ------------------------------------------------------------ 双源交叉

def _publish_from_platform(db, platform_name: str, data: dict, url: str):
    platform = db.query(SourcePlatform).filter(SourcePlatform.name == platform_name).first()
    if platform is None:
        platform = SourcePlatform(name=platform_name, platform_type="third_party", base_url="https://example.com")
        db.add(platform)
        db.commit()
        db.refresh(platform)
    page = create_source_page(db, platform.id, url)
    raw = archive_raw_document(db, page, "text", "<html></html>")
    task = create_extraction_review(db, raw, data, confidence=0.9, extractor="llm")
    return task


def test_dual_source_requires_two_platforms():
    db = SessionLocal()
    try:
        # 单平台发布 → False
        task1 = _publish_from_platform(db, "慧择网", _draft_data(), "https://www.huize.com/apps/cps/index/product/detail?prodId=1")
        assert task1.status == "approved"
        product = db.query(Product).filter(Product.name == "泰康全能保2026").first()
        assert product is not None
        assert product.dual_source_verified is False  # approve 钩子已回算

        # 第二平台发布同一产品（精确匹配更新）→ True
        task2 = _publish_from_platform(
            db, "开心保",
            {**_draft_data(), "premium_min": 210},
            "https://www.kaixinbao.com/yiwai-baoxian/999999.shtml",
        )
        assert task2.status == "approved"
        db.refresh(product)
        assert product.dual_source_verified is True
    finally:
        db.close()


def test_dual_source_ignores_review_platform():
    db = SessionLocal()
    try:
        _publish_from_platform(db, "慧择网", _draft_data(), "https://www.huize.com/apps/cps/index/product/detail?prodId=1")
        platform = SourcePlatform(name="深蓝保", platform_type="third_party_review", base_url="https://www.shenlanbao.com")
        db.add(platform)
        db.commit()
        db.refresh(platform)
        page = create_source_page(db, platform.id, "https://www.shenlanbao.com/pingce/1")
        raw = archive_raw_document(db, page, "text", "<html></html>")
        # 精确同名（仅保费差异）→ 自动发布为更新；但来源是 review 平台，不计入双源
        task = create_extraction_review(db, raw, {**_draft_data(), "premium_min": 210}, confidence=0.9, extractor="llm")
        assert task.status == "approved"
        product = db.query(Product).filter(Product.name == "泰康全能保2026").first()
        db.refresh(product)
        # 慧择 + 深蓝保（review 源不计）→ 仍为 False
        assert product.dual_source_verified is False
    finally:
        db.close()


# ------------------------------------------------------------ 深蓝保佐证

def test_extract_articles_parses_title_signals():
    # 文章页形态：【产品名】公司 …-险种-深蓝保
    html_full = """
    <a href="/pingce/1410351806239555584" class="item">【康乐福】复星联合健康 康乐福怎么样？-重疾险-深蓝保</a>
    <a href="/pingce/1442519603065520128">【大护甲8号】人保财险 大护甲8号怎么样？-意外险-深蓝保</a>
    """
    articles = re_ev.extract_articles(html_full)
    assert len(articles) == 2
    by_url = {a["url"]: a for a in articles}
    kang = by_url["https://www.shenlanbao.com/pingce/1410351806239555584"]
    assert kang["product_name"] == "康乐福"
    assert kang["insurance_type"] == "重疾险"
    hu = by_url["https://www.shenlanbao.com/pingce/1442519603065520128"]
    assert hu["product_name"] == "大护甲8号"
    assert hu["insurance_type"] == "意外险"


def test_extract_articles_list_anchor_is_product_name():
    # 列表页形态（实测）：锚文本即产品短名，无【】无险种；导航锚文本排除
    html_list = """
    <a href="/pingce/1500000000000000001">达尔文12号</a>
    <a href="/pingce/1500000000000000002">大黄蜂17号（全能版）</a>
    <a href="/pingce/1500000000000000003">查看详情</a>
    <a href="/zhishi/news">导航链接不匹配</a>
    """
    articles = re_ev.extract_articles(html_list)
    assert len(articles) == 2
    names = {a["product_name"] for a in articles}
    assert names == {"达尔文12号", "大黄蜂17号（全能版）"}


def test_match_article_name_and_type_signals():
    product = Product(name="复星联合健康康乐福重大疾病保险", company="复星联合健康", type="重疾险")
    articles = [
        {"url": "https://www.shenlanbao.com/pingce/1", "title": "【康乐福】复星联合健康 康乐福怎么样？-重疾险-深蓝保", "product_name": "康乐福", "insurance_type": "重疾险"},
        # 名称匹配但险种不符 → 不匹配
        {"url": "https://www.shenlanbao.com/pingce/2", "title": "【康乐福】康乐福意外款怎么样？-意外险-深蓝保", "product_name": "康乐福", "insurance_type": "意外险"},
    ]
    matched = re_ev.match_article_for_product(product, articles)
    assert matched is not None and matched["url"].endswith("/pingce/1")

    other = Product(name="完全无关产品", company="某公司", type="医疗险")
    assert re_ev.match_article_for_product(other, articles) is None


def test_match_reviews_to_products_populates_fields(monkeypatch):
    db = SessionLocal()
    try:
        ensure_seed_sources(db)  # 深蓝保平台
        db.add(Product(name="复星联合健康康乐福重大疾病保险", company="复星联合健康", type="重疾险", status=1,
                       premium_min=3000, premium_max=6000, sum_insured_max=50))
        db.commit()

        html = '<a href="/pingce/1410351806239555584">【康乐福】复星联合健康 康乐福怎么样？-重疾险-深蓝保</a>'
        monkeypatch.setattr(re_ev, "fetch_source_page", lambda page: FetchResult(text="t", html=html, http_status=200))
        result = re_ev.match_reviews_to_products(db)
        assert result["matched"] == 1
        product = db.query(Product).filter(Product.name.like("%康乐福%")).first()
        assert product.third_party_review_url == "https://www.shenlanbao.com/pingce/1410351806239555584"
        assert "康乐福" in product.third_party_review_title

        # 已有关联的产品不重复匹配
        monkeypatch.setattr(re_ev, "fetch_source_page", lambda page: FetchResult(text="t", html="", http_status=200))
        assert re_ev.match_reviews_to_products(db)["matched"] == 0
    finally:
        db.close()


# ------------------------------------------------------------ 推荐徽标字段贯通

def test_recommend_api_carries_verification_fields():
    from fastapi.testclient import TestClient
    from backend.main import app

    db = SessionLocal()
    try:
        product = Product(
            name="泰康全能保2026", company="泰康在线", type="意外险", status=1,
            premium_min=200, premium_max=400, sum_insured_max=100,
            official_verification_status="verified",
            dual_source_verified=True,
            third_party_review_url="https://www.shenlanbao.com/pingce/1",
            third_party_review_title="【全能保】测评",
        )
        db.add(product)
        db.flush()
        db.add(Rule(product_id=product.id, min_age=18, max_age=65, job_class_limit=6,
                    waiting_period_days=0, health_disclosure_count=3))
        db.commit()

        with TestClient(app) as client:
            payload = {
                "age": 30, "gender": "male", "annual_income": 200000, "job_class": 2,
                "life_stage": "single", "family_burden": "none",
                "health_status": "standard", "health_issues": [], "existing_coverage": [],
                "budget_ratio": 0.08, "preferred_companies": [], "enable_llm_engine": False,
            }
            response = client.post("/api/recommend", json=payload)
            assert response.status_code == 200, response.text
            products = [p for pkg in response.json()["packages"] for p in pkg["products"]]
            assert products, "真实产品应进入推荐方案"
            top = products[0]
            assert top["official_verified"] is True
            assert top["dual_source_verified"] is True
            assert top["third_party_review_url"] == "https://www.shenlanbao.com/pingce/1"
            assert top["third_party_review_title"] == "【全能保】测评"
    finally:
        db.close()
