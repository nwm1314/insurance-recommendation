"""TASK-020 regression suite: profile consumption, health matching, AI semantics.

Covers: existing_coverage soft marks/ordering, preferred_type promotion and
ordering, recognized/unknown health conditions, typical profile regression,
traceable recommendation reasons, and AI naming vs actual capability.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(tempfile.gettempdir(), 'insurance_profile_consumption_pytest.db').replace(os.sep, '/')}",
)
os.environ.setdefault("DISABLE_SCHEDULER_IN_TESTS", "true")

try:
    os.remove(os.path.join(tempfile.gettempdir(), "insurance_profile_consumption_pytest.db"))
except OSError:
    pass

import pytest

from fastapi.testclient import TestClient

from backend.main import app
from backend.app.database import SessionLocal, init_db

init_db()
from backend.app.engine.health import (
    HEALTH_ISSUE_CATALOG,
    analyze_health_issues,
    evaluate_health_match,
    normalize_health_issues,
)
from backend.app.engine.models import ScoredProduct, UserProfile
from backend.app.engine.rule_engine import (
    PREFERRED_TYPE_LABELS,
    evaluate_coverage_duplicate,
    filter_candidate_pool_with_profile,
    filter_candidate_pool_with_reasons,
    get_allowed_types,
    normalize_preferred_type,
    preferred_type_priority,
)
from backend.app.engine.ai_engine import (
    STRUCTURED_SYSTEM_PROMPT,
    _build_products_text,
    _build_user_text,
    validate_ai_output,
)
from backend.app.models.benefit import Benefit
from backend.app.models.product import Product
from backend.app.models.rule import Rule


# HomePage HEALTH_OPTIONS 的全部 value（70 项）——与后端目录逐项一致性的回归锚点
FRONTEND_HEALTH_CODES = [
    "hypertension_l1", "hypertension_l2", "hyperlipidemia", "chd", "arrhythmia",
    "valve_disease", "congenital_heart", "atherosclerosis",
    "diabetes_l1", "diabetes_l2", "glucose_impaired",
    "thyroid_nodule_l1", "thyroid_nodule_l2", "thyroid_dysfunction",
    "breast_nodule_l1", "breast_nodule_l2", "gout",
    "crohns_disease", "ulcerative_colitis", "gastritis_ulcer", "gerd",
    "fatty_liver_l1", "fatty_liver_l2",
    "hepatitis_b_l1", "hepatitis_b_l2", "hepatitis_other",
    "cirrhosis", "gallbladder_polyp", "gallbladder_polyp_l2",
    "pancreatitis", "liver_cyst",
    "lung_nodule_l1", "lung_nodule_l2", "asthma_l1", "asthma_l2",
    "copd", "sleep_apnea", "pulmonary_history",
    "kidney_stone_l1", "kidney_stone_l2", "nephritis", "kidney_cyst",
    "prostate", "gyn_benign", "cin", "endometriosis",
    "disc_herniation", "rheumatic", "osteoporosis", "epilepsy",
    "stroke", "neurodegenerative", "migraine",
    "benign_tumor", "cancer_remission", "cancer_active",
    "tumor_marker", "anemia_l1", "anemia_l2", "blood_abnormal", "lymphadenopathy",
    "hospitalization", "surgery_old", "surgery_recent", "organ_transplant",
    "mental_health", "long_term_medication", "bmi_abnormal", "smoking", "alcohol",
]


def _user(**overrides) -> UserProfile:
    base = dict(
        age=30, gender="male", annual_income=200000, job_class=2,
        life_stage="married_with_kids", family_burden="dual",
        health_status="standard", health_issues=[], existing_coverage=[],
        budget_ratio=0.08, preferred_companies=[], enable_llm_engine=False,
    )
    base.update(overrides)
    return UserProfile(**base)


@pytest.fixture(autouse=True)
def clean_products():
    _clear()
    yield
    _clear()


def _clear():
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
            Product(name="医疗A", company="C", type="医疗险", status=1, premium_min=400, premium_max=800, sum_insured_max=300, source_url="https://example.com/m"),
            Product(name="意外A", company="C", type="意外险", status=1, premium_min=100, premium_max=200, sum_insured_max=100, source_url="https://example.com/a"),
            Product(name="重疾A", company="C", type="重疾险", status=1, premium_min=2000, premium_max=4000, sum_insured_max=50, disease_count=120, source_url="https://example.com/c"),
            Product(name="寿险A", company="C", type="定期寿险", status=1, premium_min=500, premium_max=900, sum_insured_max=100, source_url="https://example.com/l"),
            Product(name="防癌A", company="C", type="防癌险", status=1, premium_min=300, premium_max=600, sum_insured_max=15, source_url="https://example.com/t"),
        ]
        db.add_all(products)
        db.flush()
        for product in products:
            db.add(Rule(product_id=product.id, min_age=0, max_age=70, job_class_limit=6, waiting_period_days=90))
            db.add(Benefit(product_id=product.id, benefit_type="basic", benefit_name="基础保障", benefit_amount="按条款", payment_limit="按条款"))
        db.commit()
    finally:
        db.close()


def _candidate_names(db, user) -> list[str]:
    candidates, _ = filter_candidate_pool_with_reasons(db, user)
    return [p.name for p in candidates]


# ---------------------------------------------------------------- health

def test_frontend_health_codes_all_recognized():
    analysis = analyze_health_issues(FRONTEND_HEALTH_CODES)
    recognized_codes = {item["code"] for item in analysis.recognized}
    assert len(recognized_codes) == len(FRONTEND_HEALTH_CODES)
    assert set(FRONTEND_HEALTH_CODES) - recognized_codes == set()
    assert analysis.unknown_conditions == []
    for item in analysis.recognized:
        assert item["label"]
        assert item["note"]
        assert "不作承保判断" in item["note"]
        assert item["condition"] in HEALTH_ISSUE_CATALOG


def test_unknown_conditions_explicitly_reported():
    analysis = analyze_health_issues(["unknown_issue_xyz", "自由文本未收录项"])
    assert analysis.recognized == []
    assert sorted(analysis.unknown_conditions) == ["unknown_issue_xyz", "自由文本未收录项"]


def test_mixed_recognized_and_unknown():
    analysis = analyze_health_issues(["hypertension_l1", "chd", "custom_thing"])
    conditions = {item["condition"] for item in analysis.recognized}
    assert conditions == {"hypertension", "heart_disease"}
    assert analysis.unknown_conditions == ["custom_thing"]


def test_duplicate_submissions_deduped():
    analysis = analyze_health_issues(["hypertension_l1", "hypertension_l1", "hypertension_l2"])
    assert len(analysis.recognized) == 2
    assert {item["condition"] for item in analysis.recognized} == {"hypertension"}


def test_standard_status_with_issues_not_silently_ignored():
    db = SessionLocal()
    try:
        db.add(Product(name="严格重疾", company="C", type="重疾险", status=1, premium_min=2000, premium_max=4000, sum_insured_max=50, source_url="https://example.com/c"))
        db.flush()
        product = db.query(Product).filter(Product.name == "严格重疾").first()
        db.add(Rule(product_id=product.id, min_age=0, max_age=70, job_class_limit=6,
                    waiting_period_days=90, health_requirements={"exclude": ["hepatitis_b"]}))
        db.commit()
        rule = product.rules
        user = _user(health_status="standard", health_issues=["乙肝"])
        match = evaluate_health_match(user, rule, product.type)
        assert match is not None
        assert match["severity"] == "block"
        assert "hepatitis_b" in match["issues"]
    finally:
        db.close()


def test_evaluate_health_match_block_caution_and_strict_warn():
    from types import SimpleNamespace
    rule = SimpleNamespace(
        health_requirements={"exclude": ["hepatitis_b"], "caution": ["smoking"]},
    )
    block = evaluate_health_match(_user(health_status="substandard", health_issues=["乙肝"]), rule, "重疾险")
    assert block and block["severity"] == "block"
    assert block["code"] == "health_issue_mismatch"

    caution = evaluate_health_match(_user(health_status="substandard", health_issues=["smoking"]), rule, "医疗险")
    assert caution and caution["severity"] == "warn"
    assert caution["code"] == "health_notice_risk"

    strict = evaluate_health_match(_user(health_status="substandard", health_issues=["chd"]), rule, "定期寿险")
    assert strict and strict["severity"] == "warn"

    clean = evaluate_health_match(_user(health_status="standard", health_issues=[]), rule, "重疾险")
    assert clean is None


def test_normalize_health_issues_maps_frontend_codes():
    assert normalize_health_issues(["hypertension_l2", "breast_nodule_l2", "糖尿病", "chd"]) == {
        "hypertension", "nodule", "diabetes", "heart_disease",
    }
    assert normalize_health_issues(["totally_unmapped_x"]) == set()


# ---------------------------------------------------------------- existing coverage

def test_existing_coverage_marks():
    commercial = _user(existing_coverage=["commercial"])
    assert evaluate_coverage_duplicate(commercial, "医疗险")["code"] == "duplicate_coverage"
    assert evaluate_coverage_duplicate(commercial, "重疾险")["code"] == "duplicate_coverage"
    assert evaluate_coverage_duplicate(commercial, "定期寿险")["code"] == "duplicate_coverage"

    social = _user(existing_coverage=["social"])
    medical_mark = evaluate_coverage_duplicate(social, "医疗险")
    assert medical_mark["code"] == "partial_duplicate"
    assert medical_mark["label"] == "部分重复保障"
    assert evaluate_coverage_duplicate(social, "重疾险") is None

    mixed = _user(existing_coverage=["social", "commercial"])
    assert evaluate_coverage_duplicate(mixed, "意外险")["code"] == "duplicate_coverage"

    none = _user(existing_coverage=[])
    assert evaluate_coverage_duplicate(none, "医疗险") is None


def test_existing_coverage_never_hard_excludes():
    _seed_products()
    db = SessionLocal()
    try:
        commercial = _user(existing_coverage=["commercial"])
        candidates, rejected = filter_candidate_pool_with_reasons(db, commercial)
        names = {p.name for p in candidates}
        assert {"医疗A", "意外A", "重疾A", "寿险A"} <= names
        assert all(r["reason_code"] != "duplicate_coverage" for r in rejected)
    finally:
        db.close()


def test_duplicate_covered_products_ordered_last():
    _seed_products()
    db = SessionLocal()
    try:
        social = _user(existing_coverage=["social"])
        names = _candidate_names(db, social)
        assert names[-1] == "医疗A", names
        preferred_social = _user(existing_coverage=["social"], preferred_type="重疾险")
        names2 = _candidate_names(db, preferred_social)
        assert names2[0] == "重疾A", names2
        assert names2[-1] == "医疗A", names2
    finally:
        db.close()


# ---------------------------------------------------------------- preferred type

def test_normalize_preferred_type():
    assert normalize_preferred_type("重疾险") == "重疾险"
    assert normalize_preferred_type(" 医疗险 ") == "医疗险"
    assert normalize_preferred_type("年金险") == "年金险"
    assert normalize_preferred_type("随便写的") is None
    assert normalize_preferred_type(None) is None
    assert normalize_preferred_type("") is None
    assert set(PREFERRED_TYPE_LABELS) == {"医疗险", "意外险", "重疾险", "定期寿险", "防癌险", "年金险"}


def test_preferred_type_priority():
    assert preferred_type_priority(_user(preferred_type="重疾险"), "重疾险") == 1.0
    assert preferred_type_priority(_user(preferred_type="重疾险"), "医疗险") == 0.0
    assert preferred_type_priority(_user(), "重疾险") == 0.0


def test_preferred_type_promotes_optional_only():
    # 46-55 组：定期寿险 optional，预算 3% 层级不含它 → 偏好可将其带入
    mid_age = _user(age=50, budget_ratio=0.03, preferred_type="定期寿险")
    assert "定期寿险" in get_allowed_types(mid_age)
    assert {"医疗险", "意外险", "防癌险", "定期寿险"} <= get_allowed_types(mid_age)

    # 26-35 组：防癌险 forbidden（硬规则），偏好不得覆盖
    young = _user(age=30, preferred_type="防癌险")
    assert "防癌险" not in get_allowed_types(young)

    # 非法偏好值：不影响允许集合
    bogus = _user(age=50, budget_ratio=0.03, preferred_type="超能力险")
    assert "定期寿险" not in get_allowed_types(bogus)


def test_preferred_type_orders_candidates_first():
    _seed_products()
    db = SessionLocal()
    try:
        user = _user(preferred_type="重疾险")
        names = _candidate_names(db, user)
        assert names[0] == "重疾A", names
    finally:
        db.close()


# ---------------------------------------------------------------- typical profiles regression

def test_typical_profiles_allowed_types():
    child = _user(age=12, annual_income=100000, budget_ratio=0.08)
    child_allowed = get_allowed_types(child)
    assert child_allowed == {"医疗险", "意外险", "重疾险"}

    adult = _user(age=32)
    assert {"医疗险", "意外险", "重疾险", "定期寿险"} <= get_allowed_types(adult)
    assert "防癌险" not in get_allowed_types(adult)

    senior = _user(age=60, annual_income=100000, budget_ratio=0.08, life_stage="retired")
    senior_allowed = get_allowed_types(senior)
    assert senior_allowed == {"医疗险", "意外险", "防癌险"}
    assert "重疾险" not in senior_allowed
    assert "定期寿险" not in senior_allowed

    low_budget = _user(age=32, budget_ratio=0.03)
    # required 险种不受预算层级影响，恒入池
    assert get_allowed_types(low_budget) == {"医疗险", "意外险", "重疾险", "定期寿险"}


# ---------------------------------------------------------------- traceability

def test_traceable_reasons_via_profile_assessment():
    _seed_products()
    db = SessionLocal()
    try:
        user = _user(
            existing_coverage=["commercial"],
            preferred_type="重疾险",
            health_status="substandard",
            health_issues=["hypertension_l1", "custom_x"],
        )
        candidates, rejected, profile = filter_candidate_pool_with_profile(db, user)
        assert candidates
        assert profile["health"]["unknown_conditions"] == ["custom_x"]
        assert any(c["code"] == "hypertension_l1" for c in profile["health"]["recognized"])
        assert "重疾险" in profile["coverage"]["marked_types"]
        assert "commercial" in profile["coverage"]["raw"]
        assert profile["coverage"]["labels"]["commercial"] == "已有商业保险"
        assert profile["preference"]["normalized"] == "重疾险"
        assert profile["preference"]["valid"] is True

        by_name = {a["name"]: a for a in profile["assessments"]}
        ci = by_name["重疾A"]
        assert any("险种偏好" in r for r in ci["traceable_reasons"])
        assert any("重复保障" in r for r in ci["traceable_reasons"])
        assert ci["rules"]["age_group"] == "26-35"
        assert ci["rules"]["type_allowed"] is True
        assert ci["preferred_type"]["matches"] is True
        assert ci["health_match"] is not None

        med = by_name["医疗A"]
        assert med["preferred_type"]["matches"] is False
        assert any("重复保障" in r for r in med["traceable_reasons"])

        invalid = _user(preferred_type="魔法险")
        _, _, bad_profile = filter_candidate_pool_with_profile(db, invalid)
        assert bad_profile["preference"]["valid"] is False
        assert bad_profile["preference"]["normalized"] is None
    finally:
        db.close()


def test_rejected_reasons_still_traceable():
    db = SessionLocal()
    try:
        db.add(Product(name="停售品", company="C", type="医疗险", status=0, premium_min=100, premium_max=200, sum_insured_max=100))
        db.add(Product(name="无规则品", company="C", type="医疗险", status=1, premium_min=100, premium_max=200, sum_insured_max=100))
        db.commit()
        _, rejected = filter_candidate_pool_with_reasons(db, _user())
        by_name = {r["name"]: r for r in rejected}
        assert by_name["停售品"]["reason_code"] == "inactive"
        assert by_name["无规则品"]["reason_code"] == "missing_rule"
    finally:
        db.close()


# ---------------------------------------------------------------- AI semantics

def test_api_recommend_accepts_coverage_preference_and_unknown_health():
    _seed_products()
    with TestClient(app) as client:
        payload = {
            "age": 30,
            "gender": "male",
            "annual_income": 200000,
            "job_class": 2,
            "life_stage": "married_with_kids",
            "family_burden": "dual",
            "health_status": "substandard",
            "health_issues": ["hypertension_l1", "mystery_condition"],
            "existing_coverage": ["commercial"],
            "budget_ratio": 0.08,
            "preferred_type": "重疾险",
            "preferred_companies": [],
            "enable_llm_engine": False,
        }
        response = client.post("/api/recommend", json=payload)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["engine_mode"] == "rule"
        assert data["packages"]
        assert data["disclaimer"]
        # unknown 健康项不破坏规则推荐；引擎层显式报告 unknown_conditions
        from backend.app.engine.rule_engine import filter_candidate_pool_with_profile
        db = SessionLocal()
        try:
            user = UserProfile(**{k: v for k, v in payload.items() if k != "enable_llm_engine"})
            user.enable_llm_engine = False
            _, _, profile = filter_candidate_pool_with_profile(db, user)
            assert profile["health"]["unknown_conditions"] == ["mystery_condition"]
        finally:
            db.close()


def test_ai_prompt_claims_no_selection_power():
    assert "规则引擎" in STRUCTURED_SYSTEM_PROMPT
    assert "不得声称" in STRUCTURED_SYSTEM_PROMPT
    assert "由你完成选品/精排/AI 推荐" in STRUCTURED_SYSTEM_PROMPT
    assert "selected_product_ids 只能来自" in STRUCTURED_SYSTEM_PROMPT
    assert "保证承保" in STRUCTURED_SYSTEM_PROMPT
    assert "医疗诊断" in STRUCTURED_SYSTEM_PROMPT


def test_ai_output_still_whitelist_constrained():
    assert validate_ai_output('{"selected_product_ids":[1],"summary":"s"}', {1, 2}) is not None
    assert validate_ai_output('{"selected_product_ids":[3],"summary":"越权"}', {1, 2}) is None


def test_ai_user_text_includes_profile_fields_and_unknown_conditions():
    user = _user(
        existing_coverage=["social"],
        preferred_type="重疾险",
        health_status="substandard",
        health_issues=["hypertension_l1", "mystery_condition"],
    )
    text = _build_user_text(user)
    assert "已有保障" in text and "social" in text
    assert "偏好险种：重疾险" in text
    assert "已识别异常项" in text
    assert "未识别健康项" in text and "mystery_condition" in text
    assert "不构成承保判断" in text

    clean = _build_user_text(_user())
    assert "异常项：无" in clean


def test_ai_products_text_carries_traceable_reasons():
    product = ScoredProduct(
        product_id=1, name="重疾X", company="C", type="重疾险",
        premium=3000, sum_insured=50, score=82,
        recommendation_reasons=["保障责任相对完整", "品牌稳定性较好"],
        risk_warnings=[{"type": "health_notice_risk", "message": "重疾险/寿险对健康告知更严格，建议重点核对既往症和检查异常"}],
    )
    text = _build_products_text([product])
    assert "推荐依据：保障责任相对完整" in text
    assert "健康提示：重疾险/寿险对健康告知更严格" in text

    bare = _build_products_text([ScoredProduct(product_id=2, name="意外X", company="C", type="意外险", premium=100, sum_insured=20, score=70)])
    assert "规则引擎按年龄/职业/健康/预算规则纳入候选池" in bare
