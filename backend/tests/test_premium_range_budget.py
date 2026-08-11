"""TASK-016 regression suite: real quote ranges constrain budget and display.

Covers: min/max/missing-upper-bound filtering semantics, package total
range (min/max), the "never recommend a plan whose max total exceeds the
budget" boundary, and preservation of premium_max/deductible on add-on
(premium-tag) products.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(tempfile.gettempdir(), 'insurance_premium_range_pytest.db').replace(os.sep, '/')}",
)
os.environ.setdefault("DISABLE_SCHEDULER_IN_TESTS", "true")

try:
    os.remove(os.path.join(tempfile.gettempdir(), "insurance_premium_range_pytest.db"))
except OSError:
    pass

import pytest

from fastapi.testclient import TestClient

from backend.main import app
from backend.app.database import SessionLocal, init_db

init_db()
from backend.app.engine.budget import calculate_budget
from backend.app.engine.combo_builder import build_combos
from backend.app.engine.models import UserProfile
from backend.app.engine.rule_engine import (
    budget_fit_for_range,
    filter_candidate_pool_with_profile,
    filter_candidate_pool_with_reasons,
    premium_range_info,
)
from backend.app.models.benefit import Benefit
from backend.app.models.product import Product
from backend.app.models.rule import Rule

# Income 200k, ratio 0.08 -> total budget 16000; tier allocation:
# medical 0.10 (1600), accident 0.10 (1600), critical_illness 0.45 (7200),
# life 0.30 (4800). Package spend limits: budget 0.5x / star 0.8x / premium 1.0x.
TYPE_BUDGETS = {"医疗险": 1600, "意外险": 1600, "重疾险": 7200, "定期寿险": 4800}


def _user(**overrides) -> UserProfile:
    base = dict(
        age=32, gender="male", annual_income=200000, job_class=2,
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


def _add_products(*products: Product):
    db = SessionLocal()
    try:
        db.add_all(products)
        db.flush()
        for product in products:
            db.add(Rule(product_id=product.id, min_age=0, max_age=70, job_class_limit=6, waiting_period_days=90))
            db.add(Benefit(product_id=product.id, benefit_type="basic", benefit_name="基础保障", benefit_amount="按条款", payment_limit="按条款"))
        db.commit()
    finally:
        db.close()


def _seed_products():
    _add_products(
        Product(name="医疗A", company="C", type="医疗险", status=1, premium_min=400, premium_max=800, deductible=10000, sum_insured_max=300, source_url="https://example.com/m"),
        Product(name="医疗B", company="C", type="医疗险", status=1, premium_min=300, premium_max=500, deductible=5000, sum_insured_max=300, source_url="https://example.com/m2"),
        Product(name="意外A", company="C", type="意外险", status=1, premium_min=100, premium_max=200, deductible=0, sum_insured_max=100, source_url="https://example.com/a"),
        Product(name="意外B", company="C", type="意外险", status=1, premium_min=80, premium_max=150, deductible=0, sum_insured_max=100, source_url="https://example.com/a2"),
        Product(name="重疾A", company="C", type="重疾险", status=1, premium_min=2000, premium_max=4000, deductible=0, sum_insured_max=50, source_url="https://example.com/c"),
        Product(name="重疾B", company="C", type="重疾险", status=1, premium_min=1800, premium_max=3500, deductible=0, sum_insured_max=50, source_url="https://example.com/c2"),
        Product(name="寿险A", company="C", type="定期寿险", status=1, premium_min=500, premium_max=900, deductible=0, sum_insured_max=100, source_url="https://example.com/l"),
    )


def _scored_dict(product: Product) -> dict:
    """Mirror the scored-dict shape produced by api/recommend._run_rule_engine."""
    return {
        "product_id": product.id,
        "name": product.name,
        "company": product.company,
        "type": product.type,
        "premium": product.premium_min or 0,
        "premium_max": product.premium_max,
        "deductible": getattr(product, "deductible", None),
        "sum_insured": product.sum_insured_max or 0,
        "source_url": product.source_url or "",
        "score": 80.0,
        "score_detail": {},
        "risk_warnings": [],
        "company_tier": 2,
    }


def _candidates_with_assessments():
    db = SessionLocal()
    try:
        user = _user()
        candidates, rejected, profile = filter_candidate_pool_with_profile(db, user)
        return {c.name: c for c in candidates}, {a["name"]: a for a in profile["assessments"]}, rejected
    finally:
        db.close()


# ---------------------------------------------------------------- filtering

def test_filter_min_over_budget_rejected():
    _add_products(
        Product(name="贵医疗", company="C", type="医疗险", status=1, premium_min=3000, premium_max=4000, sum_insured_max=300),
    )
    db = SessionLocal()
    try:
        _, rejected = filter_candidate_pool_with_reasons(db, _user())
        by_name = {r["name"]: r for r in rejected}
        assert by_name["贵医疗"]["reason_code"] == "over_budget"
        assert "最低保费 3000 元" in by_name["贵医疗"]["reason"]
        assert "1600 元" in by_name["贵医疗"]["reason"]
    finally:
        db.close()


def test_filter_keeps_max_over_budget_products_with_fit_mark():
    _seed_products()
    _add_products(
        Product(name="医疗X", company="C", type="医疗险", status=1, premium_min=900, premium_max=50000, sum_insured_max=600, source_url="https://example.com/mx"),
    )
    candidates, assessments, rejected = _candidates_with_assessments()
    assert "医疗X" in candidates, "entry price fits budget -> must stay a candidate"
    assert all(r["reason_code"] != "over_budget" for r in rejected)
    assert assessments["医疗X"]["premium_range"] == {"premium_min": 900, "premium_max": 50000, "max_unknown": False}
    assert assessments["医疗X"]["budget_fit"] == "max_may_exceed"
    assert assessments["医疗A"]["budget_fit"] == "fit"
    assert assessments["重疾A"]["budget_fit"] == "fit"


def test_filter_missing_max_is_unknown_max():
    _seed_products()
    _add_products(
        Product(name="无上限意外", company="C", type="意外险", status=1, premium_min=100, premium_max=None, sum_insured_max=100),
    )
    candidates, assessments, _ = _candidates_with_assessments()
    assert "无上限意外" in candidates
    info = assessments["无上限意外"]["premium_range"]
    assert info["premium_min"] == 100 and info["premium_max"] is None and info["max_unknown"] is True
    assert assessments["无上限意外"]["budget_fit"] == "unknown_max"
    assert premium_range_info(candidates["无上限意外"])["max_unknown"] is True


def test_filter_missing_min_falls_back_to_max_bound():
    _add_products(
        Product(name="仅上限贵", company="C", type="医疗险", status=1, premium_min=None, premium_max=3000, sum_insured_max=300),
        Product(name="仅上限可负担", company="C", type="医疗险", status=1, premium_min=None, premium_max=1500, sum_insured_max=300),
    )
    db = SessionLocal()
    try:
        _, rejected = filter_candidate_pool_with_reasons(db, _user())
        by_name = {r["name"]: r for r in rejected}
        assert by_name["仅上限贵"]["reason_code"] == "over_budget"
        assert "最低保费 3000 元" in by_name["仅上限贵"]["reason"]
        candidates, _, profile = filter_candidate_pool_with_profile(db, _user())
        names = {p.name for p in candidates}
        assert "仅上限可负担" in names and "仅上限贵" not in names
        by_assessment = {a["name"]: a for a in profile["assessments"]}
        assert by_assessment["仅上限可负担"]["budget_fit"] == "fit"
    finally:
        db.close()


def test_filter_product_without_quote_info_is_candidate():
    _seed_products()
    _add_products(
        Product(name="无报价医疗", company="C", type="医疗险", status=1, premium_min=None, premium_max=None, sum_insured_max=300),
    )
    candidates, assessments, _ = _candidates_with_assessments()
    assert "无报价医疗" in candidates
    info = assessments["无报价医疗"]["premium_range"]
    assert info["premium_min"] is None and info["premium_max"] is None and info["max_unknown"] is True
    assert assessments["无报价医疗"]["budget_fit"] == "unknown_max"


def test_budget_fit_helper_semantics():
    _seed_products()
    db = SessionLocal()
    try:
        products = {p.name: p for p in db.query(Product).all()}
        user = _user()
        assert budget_fit_for_range(products["医疗A"], user) == "fit"
        assert budget_fit_for_range(products["重疾A"], user) == "fit"
        no_income = _user(annual_income=0)
        assert budget_fit_for_range(products["重疾A"], no_income) == "fit"
    finally:
        db.close()


# ---------------------------------------------------------------- combo totals

def test_combo_total_range_equals_sum_of_known_bounds():
    _seed_products()
    db = SessionLocal()
    try:
        user = _user()
        budget = calculate_budget(user)
        products = {p.name: p for p in db.query(Product).all()}
        scored = [_scored_dict(products[n]) for n in ["医疗A", "意外A", "重疾A", "寿险A"]]
        packages = build_combos(scored, user, budget)
        assert packages
        for pkg in packages:
            assert pkg.total_premium == round(sum(p.premium for p in pkg.products), 2)
            assert pkg.total_premium_max == round(sum(p.premium_max for p in pkg.products), 2)
            assert pkg.total_premium <= pkg.total_premium_max
            assert pkg.total_premium_max <= budget.total_budget
    finally:
        db.close()


def test_combo_never_recommends_plan_whose_max_exceeds_spend():
    _seed_products()
    _add_products(
        Product(name="医疗X", company="C", type="医疗险", status=1, premium_min=900, premium_max=50000, sum_insured_max=600),
    )
    db = SessionLocal()
    try:
        user = _user()
        budget = calculate_budget(user)
        products = {p.name: p for p in db.query(Product).all()}
        scored = [_scored_dict(products[n]) for n in ["医疗A", "医疗X", "意外A", "重疾A", "寿险A"]]
        packages = build_combos(scored, user, budget)
        assert packages
        for pkg in packages:
            names = {p.name for p in pkg.products}
            assert "医疗X" not in names, f"{pkg.tag} must not include a plan whose max total blows the spend limit"
            assert pkg.total_premium_max <= budget.total_budget
        spend_caps = {"budget": 0.5 * budget.total_budget, "star": 0.8 * budget.total_budget, "premium": 1.0 * budget.total_budget}
        for pkg in packages:
            assert pkg.total_premium_max <= spend_caps[pkg.tag]
    finally:
        db.close()


def test_combo_unknown_max_sets_total_max_none():
    _seed_products()
    db = SessionLocal()
    try:
        user = _user()
        budget = calculate_budget(user)
        products = {p.name: p for p in db.query(Product).all()}
        products["医疗A"].premium_max = None
        products["医疗A"].premium_min = 400
        db.commit()
        scored = [_scored_dict(products[n]) for n in ["医疗A", "意外A", "重疾A", "寿险A"]]
        packages = build_combos(scored, user, budget)
        assert packages
        assert "医疗A" in {p.name for pkg in packages for p in pkg.products}
        for pkg in packages:
            assert pkg.total_premium > 0
            assert pkg.total_premium_max is None, "plan with a missing upper bound cannot state an exact max"
    finally:
        db.close()


def test_combo_lower_bound_shown_when_only_min_available():
    _seed_products()
    db = SessionLocal()
    try:
        user = _user()
        budget = calculate_budget(user)
        products = {p.name: p for p in db.query(Product).all()}
        for name in ["医疗A", "医疗B", "意外A", "意外B"]:
            products[name].premium_max = None
        db.commit()
        scored = [_scored_dict(products[n]) for n in ["医疗A", "意外B", "重疾A"]]
        packages = build_combos(scored, user, budget)
        assert packages
        budget_pkg = next(p for p in packages if p.tag == "budget")
        assert budget_pkg.total_premium_max is None
        assert budget_pkg.total_premium == round(sum(p.premium for p in budget_pkg.products), 2)
    finally:
        db.close()


def test_combo_missing_min_uses_known_max_as_conservative_lower_bound():
    _seed_products()
    db = SessionLocal()
    try:
        user = _user()
        budget = calculate_budget(user)
        products = {p.name: p for p in db.query(Product).all()}
        scored = [_scored_dict(products[n]) for n in ["医疗A", "意外A", "重疾A", "寿险A"]]
        scored[0]["premium"] = None
        packages = build_combos(scored, user, budget)
        assert packages
        for pkg in packages:
            medical = next((p for p in pkg.products if p.name == "医疗A"), None)
            if medical is not None:
                assert medical.premium == 800
                assert pkg.total_premium >= medical.premium
    finally:
        db.close()


# ---------------------------------------------------------------- add-on products

def test_premium_tag_extra_products_keep_premium_max_and_deductible():
    _seed_products()
    db = SessionLocal()
    try:
        user = _user()
        budget = calculate_budget(user)
        products = {p.name: p for p in db.query(Product).all()}
        scored = [_scored_dict(products[n]) for n in ["医疗A", "医疗B", "意外A", "意外B", "重疾A", "重疾B", "寿险A"]]
        packages = build_combos(scored, user, budget)
        premium_pkg = next(p for p in packages if p.tag == "premium")
        by_name = {p.name: p for p in premium_pkg.products}
        assert {"医疗A", "医疗B", "意外A", "意外B", "重疾A", "重疾B", "寿险A"} <= set(by_name)
        extras = [p for p in premium_pkg.products if p.layer == "supplement"]
        assert {p.name for p in extras} == {"医疗B", "意外B", "重疾B"}
        medical_b = by_name["医疗B"]
        assert medical_b.premium == 300 and medical_b.premium_max == 500
        assert medical_b.deductible == 5000, "add-on product must keep its deductible"
        assert medical_b.layer == "supplement"
        for p in premium_pkg.products:
            assert p.premium_max is not None and p.deductible is not None
        assert premium_pkg.total_premium_max == round(sum(p.premium_max for p in premium_pkg.products), 2)
        assert premium_pkg.total_premium_max <= budget.total_budget
    finally:
        db.close()


# ---------------------------------------------------------------- API end-to-end

def test_api_recommend_quote_semantics_end_to_end():
    _seed_products()
    _add_products(
        Product(name="医疗X", company="C", type="医疗险", status=1, premium_min=900, premium_max=50000, deductible=20000, sum_insured_max=600),
    )
    payload = {
        "age": 32, "gender": "male", "annual_income": 200000, "job_class": 2,
        "life_stage": "married_with_kids", "family_burden": "dual",
        "health_status": "standard", "health_issues": [], "existing_coverage": [],
        "budget_ratio": 0.08, "preferred_companies": [], "enable_llm_engine": False,
    }
    with TestClient(app) as client:
        response = client.post("/api/recommend", json=payload)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["packages"]
        total_budget = data["budget_analysis"]["total_budget"]
        assert total_budget == 16000
        for pkg in data["packages"]:
            assert pkg["total_premium"] > 0
            if pkg["total_premium_max"] is not None:
                assert pkg["total_premium_max"] <= total_budget
            for product in pkg["products"]:
                assert "医疗X" != product["name"], "max-over-budget product must not be recommended"
                if product["layer"] == "supplement":
                    assert product["premium_max"] is not None
                    assert product["deductible"] is not None
        premium_pkg = next(p for p in data["packages"] if p["tag"] == "premium")
        extras = [p for p in premium_pkg["products"] if p["layer"] == "supplement"]
        expected = {
            "医疗A": (800, 10000),
            "医疗B": (500, 5000),
            "意外A": (200, 0),
            "意外B": (150, 0),
            "重疾A": (4000, 0),
            "重疾B": (3500, 0),
        }
        assert extras
        for product in extras:
            assert product["name"] in expected
            assert (product["premium_max"], product["deductible"]) == expected[product["name"]]
