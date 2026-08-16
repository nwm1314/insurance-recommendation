"""TASK-036 回归：AI 精排（在候选池白名单内真实选择与排序）。

安全边界：硬规则粗筛在先；AI 只能选白名单 ID；每险种至多 1 款；组合保费
受预算上限硬校验（known max 强制、unknown max 按下限计并标「起」）；
不承诺承保/不诊断约束保留在 prompt。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(tempfile.gettempdir(), 'insurance_ai_pick_pytest.db').replace(os.sep, '/')}",
)
os.environ.setdefault("DISABLE_SCHEDULER_IN_TESTS", "true")

try:
    os.remove(os.path.join(tempfile.gettempdir(), "insurance_ai_pick_pytest.db"))
except OSError:
    pass

from backend.app.database import SessionLocal, init_db

init_db()

from backend.app.engine.budget import calculate_budget
from backend.app.engine.combo_builder import build_ai_pick_package
from backend.app.engine.models import UserProfile
from backend.app.models.benefit import Benefit
from backend.app.models.product import Product
from backend.app.models.rule import Rule


def _product(name, type_, premium, premium_max=None, score=80):
    return {
        "product_id": abs(hash(name)) % 100000,
        "name": name, "company": "测试公司", "type": type_,
        "premium": premium, "premium_max": premium_max,
        "deductible": None, "sum_insured": 100,
        "source_url": "https://www.huize.com/x", "source_type": "aggregator",
        "official_verified": True, "dual_source_verified": False,
        "third_party_review_url": None, "third_party_review_title": None,
        "score": score, "score_detail": {"price": 15},
        "risk_warnings": [], "recommendation_reasons": ["理由"], "not_recommended_reasons": [],
    }


def _user(age=30, income=200000):
    return UserProfile(age=age, gender="male", annual_income=income, job_class=2,
                       life_stage="single", family_burden="none", health_status="standard")


def test_ai_pick_respects_whitelist_dedup_and_order():
    medical_a = _product("医疗A", "医疗险", 300)
    medical_b = _product("医疗B", "医疗险", 250)
    accident = _product("意外A", "意外险", 100)
    unknown = _product("不在池内", "重疾险", 500)
    pool = [medical_a, medical_b, accident]

    # AI 排序：医疗B 优先、医疗A 同险种被去重、白名单外 ID 被忽略
    pkg = build_ai_pick_package(
        [unknown["product_id"], medical_b["product_id"], medical_a["product_id"], accident["product_id"]],
        pool, _user(), calculate_budget(_user()),
    )
    names = [p.name for p in pkg.products]
    assert names == ["医疗B", "意外A"]
    assert pkg.tag == "ai_pick"
    assert pkg.total_premium == 350
    # TASK-034/035 字段完整拷贝
    assert pkg.products[0].source_type == "aggregator"
    assert pkg.products[0].official_verified is True


def test_ai_pick_enforces_budget_and_truncates_in_ai_order():
    # 预算 200000*0.08=16000；known max 合计超限按 AI 排序截断
    user = _user(income=200000)
    budget = calculate_budget(user)
    big = _product("重疾大", "重疾险", 5000, premium_max=15000)
    medium = _product("医疗中", "医疗险", 800, premium_max=1000)
    small = _product("意外小", "意外险", 100, premium_max=120)
    pool = [big, medium, small]

    pkg = build_ai_pick_package(
        [big["product_id"], medium["product_id"], small["product_id"]], pool, user, budget,
    )
    # big+medium max = 16000 恰好触顶后 small(min 100) 按下限可入？
    # known-max 校验：total_max(15000+1000=16000) == budget 上限时 small 放行条件是
    # total_max + 120 > 16000 → 截断。逐项断言实际行为：
    names = [p.name for p in pkg.products]
    assert names[0] == "重疾大"
    assert pkg.total_premium == big["premium"] + medium["premium"]
    assert pkg.total_premium <= budget.total_budget


def test_ai_pick_unknown_max_marks_floor_only():
    user = _user()
    budget = calculate_budget(user)
    unknown_max = _product("医疗U", "医疗险", 300, premium_max=None)
    pkg = build_ai_pick_package([unknown_max["product_id"]], [unknown_max], user, budget)
    assert pkg.products[0].name == "医疗U"
    assert pkg.total_premium_max is None  # 未披露上限 → "起/以核保为准"


def test_ai_pick_empty_selection_returns_none():
    pool = [_product("医疗A", "医疗险", 300)]
    assert build_ai_pick_package([99999], pool, _user(), calculate_budget(_user())) is None


def test_recommend_ai_mode_inserts_ai_pick_package(monkeypatch):
    """端到端：AI 选择真实进入响应（packages[0] = ai_pick）。"""
    from fastapi.testclient import TestClient

    from backend.main import app
    import backend.app.api.recommend as recommend_api
    from backend.app.config import settings
    from backend.app.engine.ai_engine import AIRecommendationExplanation, render_ai_explanation

    db = SessionLocal()
    try:
        db.add(Product(name="医疗AI", company="C", type="医疗险", status=1, premium_min=300, premium_max=600, sum_insured_max=200, source_url="https://www.huize.com/a"))
        db.add(Product(name="意外AI", company="C", type="意外险", status=1, premium_min=100, premium_max=200, sum_insured_max=100, source_url="https://www.huize.com/b"))
        db.commit()
        for p in db.query(Product).filter(Product.name.like("%AI")).all():
            db.add(Rule(product_id=p.id, min_age=18, max_age=65, job_class_limit=6, waiting_period_days=30, health_disclosure_count=3))
        db.commit()
        medical = db.query(Product).filter(Product.name == "医疗AI").first()
        accident = db.query(Product).filter(Product.name == "意外AI").first()
    finally:
        db.close()

    monkeypatch.setattr(settings, "llm_api_key", "test-key")

    def fake_ai_rerank_sync(user, candidate_pool, packages, budget_max_spend=0.0):
        by_type = {}
        for p in candidate_pool:
            by_type.setdefault(p["type"], p)
        chosen = [by_type["医疗险"]["product_id"], by_type["意外险"]["product_id"]]
        explanation = AIRecommendationExplanation(
            selected_product_ids=chosen,
            summary="AI 精选摘要",
            reasoning=["医疗保障优先", "意外险低价高杠杆"],
            risk_notes=["以健康告知和核保为准"],
            comparison_notes=[],
        )
        return render_ai_explanation(explanation), explanation

    monkeypatch.setattr(recommend_api, "ai_rerank_sync", fake_ai_rerank_sync)

    payload = {
        "age": 30, "gender": "male", "annual_income": 200000, "job_class": 2,
        "life_stage": "single", "family_burden": "none", "health_status": "standard",
        "health_issues": [], "existing_coverage": [], "budget_ratio": 0.08,
        "preferred_companies": [], "enable_llm_engine": True,
    }
    with TestClient(app) as client:
        response = client.post("/api/recommend", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["engine_mode"] == "ai"
    assert data["packages"][0]["tag"] == "ai_pick"
    assert data["packages"][0]["tag_label"] == "✨ AI 精选方案"
    picked_ids = [p["id"] for p in data["packages"][0]["products"]]
    assert picked_ids == [medical.id, accident.id]
    assert data["ai_explanation"]["selected_product_ids"] == picked_ids
    # 规则套餐仍在（AI 精选只是插入最前，不删除规则结果）
    assert len(data["packages"]) >= 2
