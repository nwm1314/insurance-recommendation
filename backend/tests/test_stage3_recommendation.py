import os
import sys
import tempfile
import json
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(tempfile.gettempdir(), 'insurance_stage3_pytest.db').replace(os.sep, '/')}",
)
os.environ.setdefault("DISABLE_SCHEDULER_IN_TESTS", "true")

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.app.database import SessionLocal
from backend.app.engine.ai_engine import AIRecommendationExplanation, render_ai_explanation, validate_ai_output
from backend.app.engine.budget import calculate_budget
from backend.app.engine.budget import calculate_sum_insured
from backend.app.engine.combo_builder import build_combos
from backend.app.engine.models import BudgetAnalysis, UserProfile
from backend.app.engine.rule_engine import filter_candidate_pool_with_reasons, get_allowed_types
from backend.app.engine.scoring import DEFAULT_TYPE_WEIGHTS, _type_weights, validate_scoring_weights_on_startup, validate_type_weights
from backend.app.models.benefit import Benefit
from backend.app.models.product import Product
from backend.app.models.rule import Rule


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clean_products():
    _clear_products()
    yield
    _clear_products()


def _clear_products():
    db = SessionLocal()
    try:
        db.query(Benefit).delete()
        db.query(Rule).delete()
        db.query(Product).delete()
        db.commit()
    finally:
        db.close()


def _seed_products():
    db = SessionLocal()
    try:
        products = [
            Product(name="医疗Smoke", company="SmokeCo", type="医疗险", status=1, premium_min=500, premium_max=800, sum_insured_max=300, source_url="https://example.com/medical"),
            Product(name="高档医疗Smoke", company="SmokeCo", type="医疗险", status=1, premium_min=900, premium_max=50000, sum_insured_max=600, source_url="https://example.com/high-medical"),
            Product(name="意外Smoke", company="SmokeCo", type="意外险", status=1, premium_min=100, premium_max=200, sum_insured_max=100, source_url="https://example.com/accident"),
            Product(name="少儿重疾Smoke", company="SmokeCo", type="重疾险", status=1, premium_min=1000, premium_max=2000, sum_insured_max=50, disease_count=120, source_url="https://example.com/ci"),
            Product(name="乙肝严格重疾Smoke", company="SmokeCo", type="重疾险", status=1, premium_min=1200, premium_max=2200, sum_insured_max=50, disease_count=120, source_url="https://example.com/hb-ci"),
            Product(name="超预算重疾Smoke", company="SmokeCo", type="重疾险", status=1, premium_min=99999, premium_max=120000, sum_insured_max=100, disease_count=120, source_url="https://example.com/expensive-ci"),
            Product(name="寿险Smoke", company="SmokeCo", type="定期寿险", status=1, premium_min=300, premium_max=500, sum_insured_max=100, source_url="https://example.com/life"),
        ]
        db.add_all(products)
        db.flush()
        for product in products:
            health_requirements = {"exclude": ["hepatitis_b"]} if product.name == "乙肝严格重疾Smoke" else []
            db.add(Rule(product_id=product.id, min_age=0, max_age=60, job_class_limit=6, waiting_period_days=90, health_requirements=health_requirements))
            db.add(Benefit(product_id=product.id, benefit_type="basic", benefit_name="基础保障", benefit_amount="100万", payment_limit="按条款"))
        db.commit()
    finally:
        db.close()


def _base_payload():
    return {
        "age": 12,
        "gender": "male",
        "annual_income": 100000,
        "job_class": 1,
        "life_stage": "single",
        "family_burden": "none",
        "health_status": "standard",
        "health_issues": [],
        "existing_coverage": [],
        "budget_ratio": 0.08,
        "preferred_companies": [],
        "enable_llm_engine": False,
    }


def test_stage3_scoring_budget_and_ai_invariants():
    assert _type_weights("医疗险")["coverage"] != _type_weights("定期寿险")["coverage"]
    assert abs(sum(DEFAULT_TYPE_WEIGHTS["医疗险"].values()) - 1.0) < 0.0001
    assert validate_type_weights() == []
    assert abs(sum(_type_weights("医疗险").values()) - 1.0) < 0.0001

    child = UserProfile(age=12, gender="male", annual_income=100000, job_class=1, life_stage="single", family_burden="none", health_status="standard")
    assert "定期寿险" not in get_allowed_types(child)

    adult = UserProfile(age=32, gender="male", annual_income=200000, job_class=2, life_stage="married_with_kids", family_burden="dual", health_status="standard")
    budget = BudgetAnalysis(annual_income=200000, total_budget=16000, allocation={})
    combos = build_combos([
        {"product_id": 1, "name": "医疗A", "company": "A", "type": "医疗险", "premium": 800, "sum_insured": 300, "score": 80, "score_detail": {}, "risk_warnings": []},
        {"product_id": 2, "name": "意外A", "company": "A", "type": "意外险", "premium": 200, "sum_insured": 100, "score": 70, "score_detail": {}, "risk_warnings": []},
    ], adult, budget)
    assert combos
    assert combos[0].budget_utilization > 0
    assert combos[0].completeness_score < 1
    assert combos[0].coverage_gap_notes

    senior = UserProfile(age=60, gender="female", annual_income=100000, job_class=1, life_stage="retired", family_burden="none", health_status="standard")
    senior_budget = calculate_budget(senior)
    assert "cancer" in senior_budget.allocation
    assert abs(sum(senior_budget.allocation.values()) - 1.0) < 0.001

    valid_ai = validate_ai_output(
        '{"selected_product_ids":[1],"summary":"方案摘要","reasoning":["保障完整"],"risk_notes":["以核保为准"],"comparison_notes":[]}',
        {1, 2},
    )
    assert valid_ai is not None
    assert "方案摘要" in render_ai_explanation(valid_ai)
    assert validate_ai_output('{"selected_product_ids":[999],"summary":"越权"}', {1, 2}) is None


def test_invalid_scoring_weight_config_falls_back_to_defaults(monkeypatch):
    import backend.app.engine.scoring as scoring

    original = scoring.SCORING_WEIGHTS.copy()
    monkeypatch.setattr(scoring.settings, "scoring_weights_fail_fast", False)
    monkeypatch.setattr(scoring, "SCORING_WEIGHTS", {
        "weights": {"coverage": 1.0},
        "type_weights": {"医疗险": {"coverage": 2.0}},
    })

    try:
        errors = validate_scoring_weights_on_startup()
        weights = _type_weights("医疗险")
    finally:
        monkeypatch.setattr(scoring, "SCORING_WEIGHTS", original)

    assert errors
    assert weights == DEFAULT_TYPE_WEIGHTS["医疗险"]


def test_invalid_scoring_weight_config_can_fail_fast(monkeypatch):
    import backend.app.engine.scoring as scoring

    original = scoring.SCORING_WEIGHTS.copy()
    monkeypatch.setattr(scoring.settings, "scoring_weights_fail_fast", True)
    monkeypatch.setattr(scoring, "SCORING_WEIGHTS", {"weights": {}, "type_weights": {}})

    try:
        with pytest.raises(RuntimeError, match="scoring_weights.yaml 配置异常"):
            validate_scoring_weights_on_startup()
    finally:
        monkeypatch.setattr(scoring, "SCORING_WEIGHTS", original)
        monkeypatch.setattr(scoring.settings, "scoring_weights_fail_fast", False)


def test_recommendation_api_stage3_filters_and_response(client):
    _seed_products()
    payload = _base_payload()

    db = SessionLocal()
    try:
        user = UserProfile(**payload)
        candidates, rejected = filter_candidate_pool_with_reasons(db, user)
        assert "高档医疗Smoke" in {product.name for product in candidates}
        assert any(item["name"] == "超预算重疾Smoke" and item["reason_code"] == "over_budget" for item in rejected)
    finally:
        db.close()

    response = client.post("/api/recommend", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()
    assert any("未成年人" in item for item in data["hard_rule_summary"])
    assert data["packages"]
    assert "budget_utilization" in data["packages"][0]
    assert "completeness_score" in data["packages"][0]
    assert "定期寿险" not in {p["type"] for pkg in data["packages"] for p in pkg["products"]}
    assert any(item["reason_code"] == "over_budget" for item in data["not_recommended_summary"])
    assert any(item["name"] == "超预算重疾Smoke" and item["reason_code"] == "over_budget" for item in data["not_recommended_details"])


def test_health_and_cancer_budget_filters(client):
    _seed_products()
    payload = _base_payload()

    db = SessionLocal()
    try:
        db.add(Product(name="防癌Smoke", company="SmokeCo", type="防癌险", status=1, premium_min=300, premium_max=800, sum_insured_max=15, source_url="https://example.com/cancer"))
        db.add(Product(name="超预算防癌Smoke", company="SmokeCo", type="防癌险", status=1, premium_min=9999, premium_max=12000, sum_insured_max=15, source_url="https://example.com/expensive-cancer"))
        db.flush()
        for product in db.query(Product).filter(Product.type == "防癌险").all():
            if product.rules is None:
                db.add(Rule(product_id=product.id, min_age=0, max_age=80, job_class_limit=6, waiting_period_days=90))
                db.add(Benefit(product_id=product.id, benefit_type="basic", benefit_name="癌症保障", benefit_amount="15万", payment_limit="按条款"))
        db.commit()

        senior_payload = {**payload, "age": 60, "life_stage": "retired", "annual_income": 100000, "budget_ratio": 0.08}
        candidates, rejected = filter_candidate_pool_with_reasons(db, UserProfile(**senior_payload))
        assert "防癌Smoke" in {product.name for product in candidates}
        assert any(item["name"] == "超预算防癌Smoke" and item["reason_code"] == "over_budget" for item in rejected)
    finally:
        db.close()

    senior_response = client.post("/api/recommend", json=senior_payload)
    assert senior_response.status_code == 200, senior_response.text
    senior_data = senior_response.json()
    assert senior_data["budget_analysis"]["allocation"]["cancer"] > 0
    assert senior_data["sum_insured_advice"]["cancer"] > 0

    health_payload = {**payload, "age": 30, "health_status": "substandard", "health_issues": ["乙肝"]}
    db = SessionLocal()
    try:
        candidates, rejected = filter_candidate_pool_with_reasons(db, UserProfile(**health_payload))
        assert "乙肝严格重疾Smoke" not in {product.name for product in candidates}
        assert any(item["name"] == "乙肝严格重疾Smoke" and item["reason_code"] == "health_issue_mismatch" for item in rejected)
    finally:
        db.close()

    health_response = client.post("/api/recommend", json=health_payload)
    assert health_response.status_code == 200, health_response.text
    health_data = health_response.json()
    assert any(item["reason_code"] == "health_issue_mismatch" for item in health_data["not_recommended_details"])
    assert any(
        warning["type"] == "health_notice_risk"
        for pkg in health_data["packages"]
        for product in pkg["products"]
        for warning in product["risk_warnings"]
    )


def test_ai_explanation_is_returned_as_structured_field(client, monkeypatch):
    import backend.app.api.recommend as recommend_api
    from backend.app.config import settings

    _seed_products()
    monkeypatch.setattr(settings, "llm_api_key", "test-key")

    def fake_ai_rerank_sync(user, package_products, packages):
        explanation = AIRecommendationExplanation(
            selected_product_ids=[package_products[0].product_id],
            summary="结构化摘要",
            reasoning=["保障组合完整"],
            risk_notes=["以健康告知和核保为准"],
            comparison_notes=["医疗险负责报销，重疾险补充收入损失"],
        )
        return render_ai_explanation(explanation), explanation

    monkeypatch.setattr(recommend_api, "ai_rerank_sync", fake_ai_rerank_sync)

    payload = {**_base_payload(), "age": 30, "enable_llm_engine": True}
    response = client.post("/api/recommend", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["engine_mode"] == "ai"
    assert data["llm_narrative"]
    assert data["ai_explanation"]["summary"] == "结构化摘要"
    assert data["ai_explanation"]["selected_product_ids"]


def test_ai_mode_degrades_to_rule_when_llm_unavailable(client, monkeypatch):
    import backend.app.api.recommend as recommend_api
    from backend.app.config import settings

    _seed_products()
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    monkeypatch.setattr(recommend_api, "ai_rerank_sync", lambda user, products, packages: None)

    payload = {**_base_payload(), "age": 30, "enable_llm_engine": True}
    response = client.post("/api/recommend", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["engine_mode"] == "degraded"
    assert data["llm_narrative"]
    assert data["packages"]


def test_ai_mode_without_api_key_degrades_with_clear_narrative(client, monkeypatch):
    import backend.app.api.recommend as recommend_api
    from backend.app.config import settings

    _seed_products()
    monkeypatch.setattr(settings, "llm_api_key", "")

    payload = {**_base_payload(), "age": 30, "enable_llm_engine": True}
    response = client.post("/api/recommend", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["engine_mode"] == "degraded"
    assert "LLM API Key" in data["llm_narrative"]


def test_seed_products_if_empty_is_idempotent():
    from backend.app.data_ingestion.pipeline import ensure_seed_products_if_empty
    from backend.app.models.product import Product

    db = SessionLocal()
    try:
        assert db.query(Product).count() == 0
        ensure_seed_products_if_empty(db)
        first_count = db.query(Product).count()
        assert first_count > 100
        ensure_seed_products_if_empty(db)
        assert db.query(Product).count() == first_count
    finally:
        db.close()


def test_sse_stream_uses_safe_degraded_fallback(monkeypatch):
    import backend.app.api.recommend as recommend_api
    import backend.app.engine.ai_engine as ai_engine

    assert not hasattr(ai_engine, "ai_rerank")
    assert not hasattr(ai_engine, "ai_rerank_or_fallback")

    user = UserProfile(age=30, gender="male", annual_income=100000, job_class=1, life_stage="single", family_burden="none", health_status="standard")
    result = {
        "budget": BudgetAnalysis(annual_income=100000, total_budget=8000, allocation={}),
        "sum_insured": calculate_sum_insured(user),
        "packages": [],
        "hard_rule_summary": [],
        "coverage_gap_summary": [],
        "not_recommended_summary": [],
        "not_recommended_details": [],
    }

    async def collect_chunks():
        chunks = []
        async for chunk in recommend_api._sse_recommend_stream(user, result):
            chunks.append(chunk)
        return chunks

    chunks = asyncio.run(collect_chunks())

    assert chunks[-1] == "data: [DONE]\n\n"
    first_payload = json.loads(chunks[0].removeprefix("data: ").strip())
    assert first_payload["engine_mode"] == "degraded"
    assert first_payload["llm_narrative"]
