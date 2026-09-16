"""OPS-003：9 类人群端到端场景测试（POST /api/recommend）。

断言结构化不变量（险种覆盖/拒绝原因/标注字段）而非具体分数；
人群数据集中定义为 fixture，各人群独立建产品，禁止相互污染。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(tempfile.gettempdir(), 'insurance_persona_pytest.db').replace(os.sep, '/')}",
)
os.environ.setdefault("DISABLE_SCHEDULER_IN_TESTS", "true")

try:
    os.remove(os.path.join(tempfile.gettempdir(), "insurance_persona_pytest.db"))
except OSError:
    pass

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.app.database import SessionLocal, init_db
from backend.app.models.benefit import Benefit
from backend.app.models.product import Product
from backend.app.models.rule import Rule

init_db()


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _clear_products():
    db = SessionLocal()
    try:
        db.query(Benefit).delete()
        db.query(Rule).delete()
        db.query(Product).delete()
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def clean_products():
    _clear_products()
    yield
    _clear_products()


def _add_product(name, ptype, premium, sum_insured_wan, max_age=70, job_limit=6,
                 health_requirements=None, company="人群公司"):
    db = SessionLocal()
    try:
        product = Product(
            name=name, company=company, type=ptype, status=1,
            premium_min=premium, premium_max=premium + 200, sum_insured_max=sum_insured_wan,
            source_url=f"https://example.com/persona-{name}",
        )
        db.add(product)
        db.flush()
        db.add(Rule(product_id=product.id, min_age=0, max_age=max_age,
                    job_class_limit=job_limit, waiting_period_days=30,
                    health_requirements=health_requirements or {"exclude": [], "caution": []}))
        db.add(Benefit(product_id=product.id, benefit_type="basic", benefit_name="基础责任",
                       benefit_amount="100万", payment_limit="按条款"))
        db.commit()
    finally:
        db.close()


def _base(age, **overrides):
    payload = {
        "age": age, "gender": "male", "annual_income": 200000, "job_class": 1,
        "life_stage": "single", "family_burden": "none", "health_status": "standard",
        "health_issues": [], "existing_coverage": [], "budget_ratio": 0.08,
        "enable_llm_engine": False,
    }
    payload.update(overrides)
    return payload


def _package_types(body, tag=None):
    packages = body.get("packages") or []
    types = set()
    for pkg in packages:
        if tag and pkg["tag"] != tag:
            continue
        types |= {p["type"] for p in pkg["products"]}
    return types


# ------------------------------------------------------------ 场景 1
def test_persona_young_healthy_single(client):
    """25 岁健康单身 → 含医疗+意外；定寿不在 required（18-25 为 optional）。"""
    _add_product("年轻医疗", "医疗险", 300, 300)
    _add_product("年轻意外", "意外险", 100, 50)
    _add_product("年轻定寿", "定期寿险", 400, 100)
    resp = client.post("/api/recommend", json=_base(25))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    types = _package_types(body)
    assert {"医疗险", "意外险"} <= types
    # 18-25 定寿 optional 且全量预算层含定寿 → 允许出现；若出现必须在
    # 限寿语义下（16k 预算层含定寿），这里只断言医疗/意外恒在
    assert "防癌险" not in types or body["budget_analysis"]["total_budget"] >= 6000


# ------------------------------------------------------------ 场景 2
def test_persona_family_breadwinner_gets_life_and_gaps(client):
    """35 岁家庭支柱 → star/premium 含定寿；coverage_gaps 出现寿险建议。"""
    _add_product("支柱医疗", "医疗险", 400, 300)
    _add_product("支柱意外", "意外险", 150, 100)
    _add_product("支柱重疾", "重疾险", 1500, 50)
    _add_product("支柱定寿", "定期寿险", 600, 100)
    resp = client.post("/api/recommend", json=_base(
        35, life_stage="married_with_kids", family_burden="dual",
    ))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    star_types = _package_types(body, tag="star")
    assert "定期寿险" in star_types, "家庭支柱 star 套餐应含定寿"
    gaps = body.get("coverage_gaps") or {}
    assert "定期寿险" in gaps, "coverage_gaps 应含寿险建议"
    assert gaps["定期寿险"]["suggested"] > 0


# ------------------------------------------------------------ 场景 3
def test_persona_chronic_hepatitis_b_blocked_with_reason(client):
    """45 岁乙肝（exclude 命中）→ 重疾被拒且有 reason；risk_warnings 出现。"""
    # 45 岁乙肝（exclude 命中）→ 重疾被拒且有 reason；caution 命中的医疗
    # 仍可投但带 risk_warnings。
    _add_product("乙肝友好医疗", "医疗险", 400, 300,
                 health_requirements={"exclude": [], "caution": ["hepatitis_b"]})
    _add_product("乙肝严格重疾", "重疾险", 1500, 50,
                 health_requirements={"exclude": ["hepatitis_b"], "caution": []})
    resp = client.post("/api/recommend", json=_base(
        45, health_issues=["hepatitis_b_l1"], health_status="substandard",
    ))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    details = body.get("not_recommended_details") or []
    hb_rejects = [d for d in details if d["name"] == "乙肝严格重疾"]
    assert hb_rejects, "exclude 命中的重疾应被拒绝并给出原因"
    assert hb_rejects[0]["reason_code"], "拒绝必须有 reason_code"
    # 在池产品上的风险提示
    warnings = []
    for pkg in body.get("packages") or []:
        for p in pkg["products"]:
            warnings.extend(p.get("risk_warnings") or [])
    assert warnings, "健康异常应有 risk_warnings 提示"


# ------------------------------------------------------------ 场景 4
def test_persona_senior_low_budget_discouraged_ci(client):
    """58 岁低预算 → 重疾因险种预算被拒（非 type_forbidden，REC-003 语义）；
    防癌 optional 且保费在预算内时入池。"""
    _add_product("长者医疗", "医疗险", 500, 200, max_age=70)
    _add_product("长者意外", "意外险", 200, 50, max_age=70)
    _add_product("长者重疾", "重疾险", 2500, 30, max_age=65)
    _add_product("长者防癌", "防癌险", 250, 30, max_age=75)
    resp = client.post("/api/recommend", json=_base(
        58, annual_income=220000, budget_ratio=0.03, life_stage="retired",
    ))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    rejects = {d["name"]: d["reason_code"] for d in (body.get("not_recommended_details") or [])}
    if "长者重疾" in rejects:
        assert rejects["长者重疾"] != "type_forbidden", "56+ 重疾不再绝对禁止（REC-003）"
    names = {p["name"] for pkg in body["packages"] for p in pkg["products"]}
    assert "长者医疗" in names
    assert "长者防癌" in names, "防癌 optional 且预算内时应入池"


# ------------------------------------------------------------ 场景 5
def test_persona_elderly_no_ci_by_default(client):
    """65 岁 → 默认无重疾；防癌/医疗在池。"""
    _add_product("高龄医疗", "医疗险", 900, 200, max_age=80)
    _add_product("高龄意外", "意外险", 250, 30, max_age=80)
    _add_product("高龄重疾", "重疾险", 3000, 30, max_age=70)
    _add_product("高龄防癌", "防癌险", 700, 30, max_age=80)
    resp = client.post("/api/recommend", json=_base(65, life_stage="retired"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    allowed = _package_types(body)
    assert "重疾险" not in allowed, "65 岁默认无重疾入池（无偏好）"
    assert {"医疗险", "防癌险"} <= allowed, "防癌/医疗应在池"


# ------------------------------------------------------------ 场景 6
def test_persona_child_no_term_life(client):
    """儿童（8 岁）→ 无定寿；意外/医疗在池。"""
    _add_product("少儿医疗", "医疗险", 300, 100, max_age=17)
    _add_product("少儿意外", "意外险", 80, 20, max_age=17)
    resp = client.post("/api/recommend", json=_base(
        8, annual_income=300000, life_stage="married_with_kids",
    ))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    types = _package_types(body)
    assert "定期寿险" not in types, "未成年人硬规则不推荐定期寿险"
    assert {"医疗险", "意外险"} <= types


# ------------------------------------------------------------ 场景 7
def test_persona_high_risk_occupation_filter(client):
    """高风险职业（6 类）→ 仅 job_class_limit≥6 的产品入池。"""
    _add_product("全职业医疗", "医疗险", 400, 300, job_limit=6)
    _add_product("限2类医疗", "医疗险", 350, 300, job_limit=2)
    _add_product("全职业意外", "意外险", 120, 50, job_limit=6)
    resp = client.post("/api/recommend", json=_base(30, job_class=6))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    names = {p["name"] for pkg in body["packages"] for p in pkg["products"]}
    assert "限2类医疗" not in names
    rejects = {d["name"]: d["reason_code"] for d in (body.get("not_recommended_details") or [])}
    assert rejects.get("限2类医疗") == "job_class_not_allowed"


# ------------------------------------------------------------ 场景 8
def test_persona_existing_million_medical(client):
    """已有 300 万医疗 → duplicate 标记 + coverage_gaps 医疗 gap 为 0 或小幅。"""
    _add_product("补充医疗", "医疗险", 400, 300)
    _add_product("基础意外", "意外险", 120, 50)
    resp = client.post("/api/recommend", json=_base(
        30, existing_policies=[{"type": "医疗险", "sum_insured": 3000000, "annual_premium": 300}],
    ))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    gaps = body.get("coverage_gaps") or {}
    assert gaps["医疗险"]["gap"] <= gaps["医疗险"]["suggested"] * 0.1, (
        "已有 300 万医疗时医疗缺口应为 0 或小幅"
    )
    assessments = body.get("profile_assessment", {}).get("assessments") or []
    med_marks = [a["coverage_duplicate"]["code"] for a in assessments
                 if a["type"] == "医疗险" and a.get("coverage_duplicate")]
    assert med_marks, "已有同类保单应产生重复保障标记"


# ------------------------------------------------------------ 场景 9
def test_persona_existing_high_ci_coverage(client):
    """已有 80 万重疾 → 重疾 gap 缩小 + 升级版重复提示（high_existing_coverage）。"""
    _add_product("重疾候选", "重疾险", 1500, 50)
    _add_product("生活意外", "意外险", 120, 50)
    resp = client.post("/api/recommend", json=_base(
        32, existing_policies=[{"type": "重疾险", "sum_insured": 800000, "annual_premium": 3000}],
    ))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    gaps = body.get("coverage_gaps") or {}
    suggested_ci = gaps["重疾险"]["suggested"]
    assert gaps["重疾险"]["gap"] == max(0, suggested_ci - 800000), "缺口应按已有 80 万扣减"
    assessments = body.get("profile_assessment", {}).get("assessments") or []
    ci_codes = [a["coverage_duplicate"]["code"] for a in assessments
                if a["type"] == "重疾险" and a.get("coverage_duplicate")]
    assert "high_existing_coverage" in ci_codes, "80 万 ≥ 建议保额 50% 应升级重复提示"
