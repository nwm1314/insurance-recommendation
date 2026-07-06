"""API smoke checks for stage-3 recommendation response fields and hard rules.

Run from backend directory with a temporary DATABASE_URL:
  python scripts/recommendation_api_stage3_smoke.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi.testclient import TestClient

from backend.main import app
from backend.app.database import SessionLocal
from backend.app.models.benefit import Benefit
from backend.app.models.product import Product
from backend.app.models.rule import Rule
from backend.app.engine.models import UserProfile
from backend.app.engine.rule_engine import filter_candidate_pool_with_reasons


def seed_products():
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


def main():
    payload = {
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

    with TestClient(app) as client:
        seed_products()
        db = SessionLocal()
        try:
            user = UserProfile(**payload)
            candidates, rejected = filter_candidate_pool_with_reasons(db, user)
            candidate_names = {product.name for product in candidates}
            assert "高档医疗Smoke" in candidate_names
            assert any(item["name"] == "超预算重疾Smoke" and item["reason_code"] == "over_budget" and "最低保费" in item["reason"] for item in rejected)
        finally:
            db.close()

        response = client.post("/api/recommend", json=payload)
        assert response.status_code == 200, response.text
        data = response.json()
        assert "hard_rule_summary" in data
        assert any("未成年人" in item for item in data["hard_rule_summary"])
        assert "coverage_gap_summary" in data
        assert "not_recommended_summary" in data
        assert "not_recommended_details" in data
        assert data["packages"]
        first_package = data["packages"][0]
        assert "budget_utilization" in first_package
        assert "completeness_score" in first_package
        product_types = {p["type"] for pkg in data["packages"] for p in pkg["products"]}
        assert "定期寿险" not in product_types
        assert any(item["reason_code"] == "over_budget" and "最低保费" in item["reason"] for item in data["not_recommended_summary"])
        assert any(item["name"] == "超预算重疾Smoke" and item["reason_code"] == "over_budget" for item in data["not_recommended_details"])
        assert all("recommendation_reasons" in p for pkg in data["packages"] for p in pkg["products"])

        senior_payload = {
            **payload,
            "age": 60,
            "life_stage": "retired",
            "annual_income": 100000,
            "budget_ratio": 0.08,
        }
        db = SessionLocal()
        try:
            db.add(Product(name="防癌Smoke", company="SmokeCo", type="防癌险", status=1, premium_min=300, premium_max=800, sum_insured_max=15, source_url="https://example.com/cancer"))
            db.add(Product(name="超预算防癌Smoke", company="SmokeCo", type="防癌险", status=1, premium_min=9999, premium_max=12000, sum_insured_max=15, source_url="https://example.com/expensive-cancer"))
            db.flush()
            cancer_products = db.query(Product).filter(Product.type == "防癌险").all()
            for product in cancer_products:
                if product.rules is None:
                    db.add(Rule(product_id=product.id, min_age=0, max_age=80, job_class_limit=6, waiting_period_days=90))
                    db.add(Benefit(product_id=product.id, benefit_type="basic", benefit_name="癌症保障", benefit_amount="15万", payment_limit="按条款"))
            db.commit()

            user = UserProfile(**senior_payload)
            candidates, rejected = filter_candidate_pool_with_reasons(db, user)
            candidate_names = {product.name for product in candidates}
            assert "防癌Smoke" in candidate_names
            assert any(item["name"] == "超预算防癌Smoke" and item["reason_code"] == "over_budget" and "最低保费" in item["reason"] for item in rejected)
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
            user = UserProfile(**health_payload)
            candidates, rejected = filter_candidate_pool_with_reasons(db, user)
            candidate_names = {product.name for product in candidates}
            assert "乙肝严格重疾Smoke" not in candidate_names
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
    print("recommend api stage3 smoke ok")


if __name__ == "__main__":
    main()
