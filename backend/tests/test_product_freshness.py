"""PROD-003 回归：产品数据新鲜度标注（data_stale / last_verified_at）真实生效。

评审将 `data_stale` / `last_verified_at` 的实际生效情况列为**待验证假设**（无实测）。
本文件用反例实证把它变成已证结论：

* 未复核（`last_verified_at is None`）-> `data_stale=True`；
* 复核时间早于 `data_stale_days`（默认 90 天）-> `data_stale=True`；
* 刚复核过 -> `data_stale=False`。

若该标注链路（`recommend._product_freshness` -> `_build_response` -> API 响应）被破坏，
或阈值判断被写反，下面的断言会立刻失败。
"""

import os
import sys
import tempfile
from datetime import timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(tempfile.gettempdir(), 'insurance_freshness_pytest.db').replace(os.sep, '/')}",
)
os.environ.setdefault("DISABLE_SCHEDULER_IN_TESTS", "true")

try:
    os.remove(os.path.join(tempfile.gettempdir(), "insurance_freshness_pytest.db"))
except OSError:
    pass

import pytest
from fastapi.testclient import TestClient

from backend.app.database import SessionLocal, init_db

init_db()

from backend.app.models.benefit import Benefit
from backend.app.models.product import Product
from backend.app.models.rule import Rule
from backend.app.time import utc_now
from backend.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _clean_db():
    db = SessionLocal()
    try:
        db.query(Benefit).delete()
        db.query(Rule).delete()
        db.query(Product).delete()
        db.commit()
    finally:
        db.close()


def _payload():
    return {
        "age": 30,
        "gender": "male",
        "annual_income": 200000,
        "job_class": 1,
        "life_stage": "single",
        "family_burden": "none",
        "health_status": "standard",
        "health_issues": [],
        "existing_coverage": [],
        "budget_ratio": 0.1,
        "preferred_companies": [],
        "enable_llm_engine": False,
    }


def _seed_with_verified_at(verified_at):
    """写入一个医疗险产品，可按需设置 last_verified_at。"""
    db = SessionLocal()
    try:
        product = Product(
            name="新鲜度测试医疗险",
            company="新鲜度测试公司",
            type="医疗险",
            status=1,
            premium_min=350,
            premium_max=780,
            deductible=10000,
            sum_insured_max=400,
            source_url="https://example.com/freshness",
            last_verified_at=verified_at,
        )
        db.add(product)
        db.flush()
        db.add(Rule(
            product_id=product.id, min_age=0, max_age=80,
            job_class_limit=6, waiting_period_days=30,
        ))
        db.add(Benefit(
            product_id=product.id, benefit_type="basic",
            benefit_name="基础保障", benefit_amount="400万", payment_limit="按条款",
        ))
        db.commit()
    finally:
        db.close()


def _first_product(client):
    resp = client.post("/api/recommend", json=_payload())
    assert resp.status_code == 200, resp.text
    products = [p for pkg in resp.json()["packages"] for p in pkg["products"]]
    assert products, "候选池不应为空，否则无法验证新鲜度标注"
    return products[0]


def test_never_verified_product_is_marked_stale(client):
    """从未复核的产品必须标注 data_stale=True 且 last_verified_at 为 None。"""
    _seed_with_verified_at(None)
    product = _first_product(client)
    assert product["data_stale"] is True, "缺少复核时间应视为过期"
    assert product["last_verified_at"] is None


def test_product_verified_long_ago_is_marked_stale(client):
    """复核时间早于阈值（默认 90 天）必须标注 data_stale=True。"""
    from backend.app.config import settings

    stale_days = settings.data_stale_days + 10
    _seed_with_verified_at(utc_now() - timedelta(days=stale_days))
    product = _first_product(client)
    assert product["data_stale"] is True, f"超过 {settings.data_stale_days} 天未复核应标注过期"
    assert product["last_verified_at"] is not None, "应回传复核时间供展示"


def test_recently_verified_product_is_not_stale(client):
    """刚复核过的产品必须标注 data_stale=False（对照，防止阈值判断写反）。"""
    _seed_with_verified_at(utc_now() - timedelta(days=1))
    product = _first_product(client)
    assert product["data_stale"] is False, "1 天前复核不应视为过期"
    assert product["last_verified_at"] is not None


def test_threshold_boundary_is_strictly_greater_than(client):
    """阈值边界：恰好等于 data_stale_days 天时**不**算过期（实现为 > 而非 >=）。

    该边界是实现约定（`(utc_now() - verified_at).days > settings.data_stale_days`），
    锁定它可避免后续改动无意中收紧或放宽判定。
    """
    from backend.app.config import settings

    _seed_with_verified_at(utc_now() - timedelta(days=settings.data_stale_days))
    product = _first_product(client)
    assert product["data_stale"] is False, (
        f"恰好 {settings.data_stale_days} 天不应判为过期（边界为严格大于）"
    )
