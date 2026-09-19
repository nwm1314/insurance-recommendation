"""DEV-006 回归：金额字段的四层单位口径一致性。

提示词 §5.1 明确本项目的口径约定：

* `products.sum_insured_max` 存储单位 = **万**（DB → 引擎 → API 全链路保持万）；
* `premium_*` / `deductible` 单位 = **元**；
* `sum_insured_advice.*`（建议保额）单位 = **元**，由展示层除以 10000 显示为万；
* `existing_policies.sum_insured`（用户填写的已有保单）单位 = **元**。

评审将"四层是否真的统一"列入待验证假设；本文件用**反例实证**把它变成已证结论：
直接构造一个"医疗险保额 400 万 / 年保费 350 元 / 免赔额 10000 元"的产品，断言
API 各字段的单位标签与预期一致，从而锁死口径漂移。
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(tempfile.gettempdir(), 'insurance_units_pytest.db').replace(os.sep, '/')}",
)
os.environ.setdefault("DISABLE_SCHEDULER_IN_TESTS", "true")

try:
    os.remove(os.path.join(tempfile.gettempdir(), "insurance_units_pytest.db"))
except OSError:
    pass

import pytest
from fastapi.testclient import TestClient

from backend.app.database import SessionLocal, init_db

init_db()

from backend.app.models.benefit import Benefit
from backend.app.models.product import Product
from backend.app.models.rule import Rule
from backend.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _clean_db():
    """只清本文件写入的 products（源数据由 _seed 每次重建）。

    说明：全量运行时会与其它测试文件共用同一个库（各文件用 setdefault 竞逐
    DATABASE_URL）。因此本文件不依赖"库里恰好没有 Rule/Benefit"这类全局前提，
    而是自己补齐所需的规则/保障行——否则别的文件清表后会连带影响本文件的
    候选池（实测表现为候选池为空、断言 assert products 失败）。
    """
    db = SessionLocal()
    try:
        db.query(Benefit).delete()
        db.query(Rule).delete()
        db.query(Product).delete()
        db.commit()
    finally:
        db.close()


# 基准产品：保额 400 **万**、年保费 350 **元**、免赔额 10000 **元**。
# 若某一层误把"万"当"元"（或反之），下面的断言会立刻失败——例如保额被再乘
# 10000 变成 4,000,000，或保费被除以 10000 变成 0.035。
_BASE_PRODUCT = dict(
    name="单位口径基准医疗险",
    company="单位测试公司",
    type="医疗险",
    status=1,
    premium_min=350,
    premium_max=780,
    deductible=10000,
    sum_insured_max=400,
    source_url="https://example.com/units",
)


def _seed():
    """写入基准产品及其规则 / 保障行。

    Rule 与 Benefit 是硬规则粗筛的输入：缺少它们时产品不会进入候选池
    （见 rule_engine.filter_candidate_pool_with_reasons），断言就会落空。
    这里显式补齐，使本文件不依赖其它测试文件留下的全局状态。
    """
    db = SessionLocal()
    try:
        product = Product(**_BASE_PRODUCT)
        db.add(product)
        db.flush()
        db.add(Rule(
            product_id=product.id,
            min_age=0,
            max_age=80,
            job_class_limit=6,
            waiting_period_days=30,
        ))
        db.add(Benefit(
            product_id=product.id,
            benefit_type="basic",
            benefit_name="基础保障",
            benefit_amount="400万",
            payment_limit="按条款",
        ))
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


def test_product_sum_insured_stays_in_wan(client):
    """存储层与 API 层的 sum_insured 必须是**万**，不得被换算成元。"""
    _seed()
    resp = client.post("/api/recommend", json=_payload())
    assert resp.status_code == 200, resp.text

    products = [p for pkg in resp.json()["packages"] for p in pkg["products"]]
    assert products, "候选池不应为空，否则本用例无法验证口径"
    for p in products:
        assert p["sum_insured"] == 400, (
            f"保额应为 400（万），实际 {p['sum_insured']}——疑似被换算成元或重复换算"
        )


def test_product_premium_and_deductible_are_in_yuan(client):
    """premium_* 与 deductible 必须是**元**，不得被换算成万。"""
    _seed()
    resp = client.post("/api/recommend", json=_payload())
    assert resp.status_code == 200, resp.text

    products = [p for pkg in resp.json()["packages"] for p in pkg["products"]]
    assert products
    for p in products:
        assert p["premium"] == 350, f"年保费应为 350（元），实际 {p['premium']}"
        assert p["premium_max"] == 780, f"年保费上限应为 780（元），实际 {p['premium_max']}"
        assert p["deductible"] == 10000, f"免赔额应为 10000（元），实际 {p['deductible']}"


def test_sum_insured_advice_is_in_yuan(client):
    """建议保额 sum_insured_advice.* 必须是**元**（展示层再除以 10000 显示为万）。"""
    _seed()
    resp = client.post("/api/recommend", json=_payload())
    assert resp.status_code == 200, resp.text

    advice = resp.json()["sum_insured_advice"]
    # 年收入 20 万：医疗险建议保额应为百万量级（单位元 → 数值 >= 1000000）。
    # 若被误按"万"存储，该值会是 100 量级，断言即可抓住。
    assert advice["medical"] >= 1_000_000, (
        f"医疗险建议保额应为元（百万量级），实际 {advice['medical']}——疑似误存为万"
    )
    # 重疾险建议 = 年收入×3 + 30 万基准 = 60 万 + 30 万 = 90 万元
    assert advice["critical_illness"] == 900_000, (
        f"重疾险建议保额应为 900000 元（20万×3 + 30万），实际 {advice['critical_illness']}"
    )


def test_budget_analysis_is_in_yuan(client):
    """预算总额必须是**元**（年收入 20 万 × 10% = 20000 元）。"""
    _seed()
    resp = client.post("/api/recommend", json=_payload())
    assert resp.status_code == 200, resp.text

    budget = resp.json()["budget_analysis"]
    assert budget["annual_income"] == 200000
    assert budget["total_budget"] == 20000, (
        f"预算总额应为 20000 元，实际 {budget['total_budget']}——疑似单位漂移"
    )
