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

try:
    os.remove(os.path.join(tempfile.gettempdir(), "insurance_stage3_pytest.db"))
except OSError:
    pass

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.app.database import SessionLocal
from backend.app.engine.ai_engine import AIRecommendationExplanation, render_ai_explanation, validate_ai_output
from backend.app.config import normalize_llm_base_url
from backend.app.engine.budget import calculate_budget
from backend.app.engine.budget import calculate_sum_insured
from backend.app.engine.combo_builder import build_combos
from backend.app.engine.models import BudgetAnalysis, UserProfile
from backend.app.engine.models import ScoredProduct
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


def test_recommend_response_has_reproducibility_meta(client):
    """DATA-002：响应 meta 四键非空（engine/rule/scoring 版本 + 权重 hash）。"""
    response = client.post("/api/recommend", json=_base_payload())
    assert response.status_code == 200, response.text
    meta = response.json()["meta"]
    assert set(meta) == {"engine_version", "rule_version", "scoring_version", "scoring_weights_hash"}
    for key, value in meta.items():
        assert value, f"meta.{key} must not be empty"
    assert meta["scoring_version"] == "2", "scoring_weights.yaml 顶层 version 应为 2"


def test_scoring_weights_hash_tracks_file_content(monkeypatch, tmp_path):
    """DATA-002：scoring_weights.yaml 内容变化时 hash 随之变化。"""
    from backend.app import config as config_module

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "scoring_weights.yaml").write_text("weights: {}\n", encoding="utf-8")
    monkeypatch.setattr(config_module, "BASE_DIR", tmp_path)
    first = config_module.scoring_weights_hash()

    (config_dir / "scoring_weights.yaml").write_text("weights: {coverage: 1.0}\n", encoding="utf-8")
    second = config_module.scoring_weights_hash()

    assert first and second and first != second


def test_data_stale_annotation_in_recommend_response(client):
    """DATA-001：复核缺失或超过 90 天的产品在推荐结果中标注 data_stale。"""
    from datetime import timedelta

    from backend.app.time import utc_now

    db = SessionLocal()
    try:
        fresh = Product(name="新鲜医疗Smoke", company="FreshCo", type="医疗险", status=1,
                        premium_min=500, premium_max=800, sum_insured_max=300,
                        last_verified_at=utc_now())
        stale = Product(name="陈旧意外Smoke", company="StaleCo", type="意外险", status=1,
                        premium_min=100, premium_max=200, sum_insured_max=100,
                        last_verified_at=utc_now() - timedelta(days=100))
        missing = Product(name="未复核寿险Smoke", company="MissCo", type="定期寿险", status=1,
                          premium_min=300, premium_max=500, sum_insured_max=100,
                          last_verified_at=None)
        db.add_all([fresh, stale, missing])
        db.flush()
        for product in (fresh, stale, missing):
            db.add(Rule(product_id=product.id, min_age=18, max_age=70, job_class_limit=6, waiting_period_days=30))
        db.commit()
    finally:
        db.close()

    payload = _base_payload()
    payload.update({"age": 30, "life_stage": "single", "budget_ratio": 0.08})
    response = client.post("/api/recommend", json=payload)
    assert response.status_code == 200, response.text
    packages = response.json()["packages"]
    assert packages, "核心三险齐全时应形成方案"
    items = {}
    for pkg in packages:
        for p in pkg["products"]:
            items.setdefault(p["name"], p)
    assert items["新鲜医疗Smoke"]["data_stale"] is False
    assert items["新鲜医疗Smoke"]["last_verified_at"] is not None
    assert items["陈旧意外Smoke"]["data_stale"] is True
    assert items["未复核寿险Smoke"]["data_stale"] is True
    assert items["未复核寿险Smoke"]["last_verified_at"] is None


def test_existing_policies_drive_coverage_gaps_and_duplicate_upgrade(client):
    """REC-001：已有保单参与缺口分析（gap=建议-已披露合计），且同险种
    达到建议保额 50% 时重复标记升级为 high_existing_coverage。"""
    db = SessionLocal()
    try:
        ci = Product(name="普通重疾Smoke", company="GapCo", type="重疾险", status=1,
                     premium_min=1000, premium_max=2000, sum_insured_max=50, disease_count=120,
                     source_url="https://example.com/ci-gap")
        db.add(ci)
        db.flush()
        db.add(Rule(product_id=ci.id, min_age=18, max_age=60, job_class_limit=6, waiting_period_days=90))
        db.commit()
    finally:
        db.close()

    payload = _base_payload()
    payload.update({"age": 30, "existing_policies": [
        {"type": "重疾险", "sum_insured": 500000, "annual_premium": 2000},
    ]})
    response = client.post("/api/recommend", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()

    gaps = body["coverage_gaps"]
    assert set(gaps) == {"医疗险", "意外险", "重疾险", "定期寿险", "防癌险"}
    suggested_ci = gaps["重疾险"]["suggested"]
    assert suggested_ci > 0
    assert gaps["重疾险"]["existing"] == 500000
    assert gaps["重疾险"]["gap"] == suggested_ci - 500000
    # 未披露保额按 0 计入
    assert gaps["医疗险"]["existing"] == 0

    # 重疾建议保额 = min(3×收入+30万, 100万) = 60万；已披露 50 万 ≥ 50% → 升级标记
    assessments = body["profile_assessment"]["assessments"]
    ci_marks = [
        a["coverage_duplicate"]
        for a in assessments
        if a["type"] == "重疾险" and a["coverage_duplicate"]
    ]
    assert ci_marks, "重疾候选应有重复保障标记"
    assert all(m["code"] == "high_existing_coverage" for m in ci_marks)
    assert "重疾险" in body["profile_assessment"]["coverage"]["marked_types"]


def test_occupation_name_resolves_job_class_for_filtering(client):
    """REC-001：未显式选择 job_class 时由 occupation_name 解析（矿工=6 类），
    6 类职业限制产品被正确过滤。"""
    db = SessionLocal()
    try:
        open_to_all = Product(name="全职业医疗Smoke", company="OccCo", type="医疗险", status=1,
                              premium_min=500, premium_max=800, sum_insured_max=300,
                              source_url="https://example.com/occ-all")
        restricted = Product(name="仅低职业医疗Smoke", company="OccCo", type="医疗险", status=1,
                             premium_min=600, premium_max=900, sum_insured_max=300,
                             source_url="https://example.com/occ-low")
        db.add_all([open_to_all, restricted])
        db.flush()
        db.add(Rule(product_id=open_to_all.id, min_age=18, max_age=60, job_class_limit=6, waiting_period_days=30))
        db.add(Rule(product_id=restricted.id, min_age=18, max_age=60, job_class_limit=2, waiting_period_days=30))
        db.commit()
    finally:
        db.close()

    payload = _base_payload()
    payload.pop("job_class")
    payload.update({"age": 30, "occupation_name": "矿工"})
    response = client.post("/api/recommend", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    rejected = {
        item["name"]
        for item in body["not_recommended_details"]
        if item["reason_code"] == "job_class_not_allowed"
    }
    assert "仅低职业医疗Smoke" in rejected, "6 类职业应被 job_class_limit=2 的产品拒绝"


def test_job_class_and_occupation_both_missing_returns_422(client):
    """REC-001：job_class 与 occupation_name 都缺失时 422，不静默猜默认值。"""
    payload = _base_payload()
    payload.pop("job_class")
    response = client.post("/api/recommend", json=payload)
    assert response.status_code == 422, response.text


def test_social_insurance_compat_and_medical_note(client):
    """REC-001：旧请求（existing_coverage 含 social）按职工社保兼容处理；
    无社保身份时医疗建议附提示文案。"""
    # 旧式：existing_coverage=["social"] → 推断 employee → 无提示
    payload = _base_payload()
    payload["existing_coverage"] = ["social"]
    response = client.post("/api/recommend", json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["sum_insured_advice"]["medical_social_note"] is None

    # 显式无社保 → 有提示
    payload = _base_payload()
    payload["social_insurance"] = "none"
    response = client.post("/api/recommend", json=payload)
    assert response.status_code == 200, response.text
    note = response.json()["sum_insured_advice"]["medical_social_note"]
    assert note and "无社保" in note


def test_legacy_request_without_new_fields_keeps_shape(client):
    """REC-001：旧请求（无新字段）行为不变——coverage_gaps 为新增展示字段，
    已有保额合计为 0、gap=建议值。"""
    payload = _base_payload()
    response = client.post("/api/recommend", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    gaps = body["coverage_gaps"]
    assert all(item["existing"] == 0 and item["gap"] == item["suggested"] for item in gaps.values())
    assert body["sum_insured_advice"]["medical_social_note"] is not None


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
    markdown_wrapped = validate_ai_output(
        '```json\n{"selected_product_ids":[2],"summary":"markdown 包裹","reasoning":["ok"],"risk_notes":[],"comparison_notes":[]}\n```',
        {1, 2},
    )
    assert markdown_wrapped is not None
    assert markdown_wrapped.summary == "markdown 包裹"
    prose_wrapped = validate_ai_output(
        '推荐如下：\n{"selected_product_ids":[1],"summary":"前后有杂文","reasoning":["ok"],"risk_notes":[],"comparison_notes":[]}\n以上是完整方案。',
        {1, 2},
    )
    assert prose_wrapped is not None
    assert prose_wrapped.summary == "前后有杂文"
    assert validate_ai_output("模型拒绝回答问题", {1, 2}) is None


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

    def fake_ai_rerank_sync(user, candidate_pool, packages, budget_max_spend=0.0):
        explanation = AIRecommendationExplanation(
            selected_product_ids=[candidate_pool[0]["product_id"]],
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
    # AI 精选套餐位于最前，且产品来自 AI 的选择
    assert data["packages"][0]["tag"] == "ai_pick"
    assert data["packages"][0]["products"][0]["id"] in data["ai_explanation"]["selected_product_ids"]


def test_ai_mode_degrades_to_rule_when_llm_unavailable(client, monkeypatch):
    import backend.app.api.recommend as recommend_api
    from backend.app.config import settings

    _seed_products()
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    monkeypatch.setattr(recommend_api, "ai_rerank_sync", lambda user, candidates, packages, budget_max_spend=0.0: None)

    payload = {**_base_payload(), "age": 30, "enable_llm_engine": True}
    response = client.post("/api/recommend", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["engine_mode"] == "degraded"
    assert data["llm_narrative"]
    assert data["packages"]


def test_ai_mode_without_api_key_degrades_with_clear_narrative(client, monkeypatch):
    from backend.app.config import settings

    _seed_products()
    monkeypatch.setattr(settings, "llm_api_key", "")

    payload = {**_base_payload(), "age": 30, "enable_llm_engine": True}
    response = client.post("/api/recommend", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["engine_mode"] == "degraded"
    assert "LLM API Key" in data["llm_narrative"]


def test_ai_rerank_disables_deepseek_thinking_and_retries_empty_content(monkeypatch):
    import backend.app.engine.ai_engine as ai_engine
    from backend.app.config import settings

    class Message:
        def __init__(self, content):
            self.content = content

    class Response:
        def __init__(self, content):
            self.choices = [type("Choice", (), {"message": Message(content)})()]

    class Completions:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            return Response(
                "" if len(self.calls) == 1 else
                '{"selected_product_ids":[1],"summary":"重试成功","reasoning":["匹配"],"risk_notes":[],"comparison_notes":[]}'
            )

    class FakeClient:
        def __init__(self, **kwargs):
            self.init_kwargs = kwargs
            self.chat = type("Chat", (), {"completions": Completions()})()

    clients = []

    def fake_openai(**kwargs):
        client_instance = FakeClient(**kwargs)
        clients.append(client_instance)
        return client_instance

    monkeypatch.setattr(ai_engine, "OpenAI", fake_openai)
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    monkeypatch.setattr(settings, "llm_base_url", "https://api.deepseek.com/v1/chat/completions")
    monkeypatch.setattr(settings, "llm_model", "deepseek-v4-flash")
    monkeypatch.setattr(settings, "llm_max_tokens", 2048)
    monkeypatch.setattr(settings, "llm_max_retries", 3)

    product = {
        "product_id": 1,
        "name": "测试产品",
        "company": "测试公司",
        "type": "医疗险",
        "premium": 500,
        "sum_insured": 300,
    }
    result = ai_engine.ai_rerank_sync(
        UserProfile(age=30, gender="male", annual_income=200000, job_class=2, life_stage="single", family_burden="none", health_status="standard"),
        [product],
    )

    assert result is not None
    assert result[0] == "重试成功\n推荐理由：匹配"
    assert clients[0].init_kwargs["max_retries"] == 3
    assert clients[0].init_kwargs["base_url"] == "https://api.deepseek.com/v1"
    assert len(clients[0].chat.completions.calls) == 2
    for call in clients[0].chat.completions.calls:
        assert call["max_tokens"] == 2048
        assert call["extra_body"] == {"thinking": {"type": "disabled"}}


def test_llm_base_url_normalizes_openai_chat_completion_suffix():
    assert normalize_llm_base_url("https://opencode.ai/zen/v1/chat/completions") == "https://opencode.ai/zen/v1"
    assert normalize_llm_base_url("https://api.deepseek.com/v1") == "https://api.deepseek.com/v1"


def test_ai_rerank_retries_without_unsupported_json_response_format(monkeypatch):
    import backend.app.engine.ai_engine as ai_engine
    from backend.app.config import settings

    class UnsupportedJsonError(Exception):
        status_code = 400

    class Message:
        content = '{"selected_product_ids":[1],"summary":"兼容网关","reasoning":[],"risk_notes":[],"comparison_notes":[]}'

    class Completions:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                raise UnsupportedJsonError("response_format json_object is unsupported")
            return type("Response", (), {"choices": [type("Choice", (), {"message": Message()})()]})()

    completions = Completions()
    fake_client = type("Client", (), {"chat": type("Chat", (), {"completions": completions})()})()
    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: fake_client)
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    monkeypatch.setattr(settings, "llm_base_url", "https://example.test/v1")
    monkeypatch.setattr(settings, "llm_model", "compatible-model")

    product = {
        "product_id": 1,
        "name": "测试产品",
        "company": "测试公司",
        "type": "医疗险",
        "premium": 500,
        "sum_insured": 300,
    }
    result = ai_engine.ai_rerank_sync(
        UserProfile(age=30, gender="male", annual_income=200000, job_class=2, life_stage="single", family_burden="none", health_status="standard"),
        [product],
    )

    assert result is not None
    assert len(completions.calls) == 2
    assert "response_format" in completions.calls[0]
    assert "response_format" not in completions.calls[1]


def test_ai_rerank_catches_client_initialization_failure(monkeypatch):
    import backend.app.engine.ai_engine as ai_engine
    from backend.app.config import settings

    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    monkeypatch.setattr(settings, "llm_model", "compatible-model")
    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("bad config")))

    product = {
        "product_id": 1,
        "name": "测试产品",
        "company": "测试公司",
        "type": "医疗险",
        "premium": 500,
        "sum_insured": 300,
    }
    assert ai_engine.ai_rerank_sync(
        UserProfile(age=30, gender="male", annual_income=200000, job_class=2, life_stage="single", family_burden="none", health_status="standard"),
        [product],
    ) is None


def test_seed_products_if_empty_is_idempotent(monkeypatch):
    from backend.app.config import settings
    from backend.app.data_ingestion.pipeline import ensure_seed_products_if_empty
    from backend.app.models.product import Product

    # TASK-034 后演示目录默认关闭（生产产品池只含真实抓取数据），
    # 显式开启以验证幂等语义。
    monkeypatch.setattr(settings, "seed_demo_products", True)
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
