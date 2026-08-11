import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(tempfile.gettempdir(), 'insurance_product_catalog_pytest.db').replace(os.sep, '/')}",
)
os.environ.setdefault("DISABLE_SCHEDULER_IN_TESTS", "true")

try:
    os.remove(os.path.join(tempfile.gettempdir(), "insurance_product_catalog_pytest.db"))
except OSError:
    pass

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.app.config import settings
from backend.app.database import SessionLocal
from backend.app.models.auth import AuditLog, RefreshToken, SavedProfile, User, UserRole
from backend.app.models.benefit import Benefit
from backend.app.models.product import Product
from backend.app.models.rule import Rule
from backend.app.services.auth_service import ensure_auth_defaults


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clean_data():
    _clean()
    yield
    _clean()


def _clean():
    db = SessionLocal()
    try:
        db.query(AuditLog).delete()
        db.query(RefreshToken).delete()
        db.query(SavedProfile).delete()
        db.query(Benefit).delete()
        db.query(Rule).delete()
        db.query(Product).delete()
        db.query(UserRole).delete()
        db.query(User).delete()
        db.commit()
    finally:
        db.close()


def _bootstrap_admin(monkeypatch):
    monkeypatch.setattr(settings, "first_admin_email", "catalog-admin@example.com")
    monkeypatch.setattr(settings, "first_admin_password", "Password12345")
    db = SessionLocal()
    try:
        ensure_auth_defaults(db)
    finally:
        db.close()


def _register(client, email, password="Password12345"):
    response = client.post("/api/auth/register", json={"email": email, "password": password, "full_name": email})
    assert response.status_code == 200, response.text
    return response.json()


def _login_token(client, email, password="Password12345"):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return client.cookies.get("access_token")


@pytest.fixture()
def admin_headers(client, monkeypatch):
    _bootstrap_admin(monkeypatch)
    token = _login_token(client, "catalog-admin@example.com")
    client.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


def _product_payload(type_value="医疗险"):
    return {
        "name": "测试医疗产品",
        "company": "测试公司",
        "type": type_value,
        "premium_min": 500,
        "premium_max": 800,
        "sum_insured_min": 100,
        "sum_insured_max": 300,
        "deductible": 10000,
        "rule": {
            "min_age": 0,
            "max_age": 60,
            "job_class_limit": 4,
            "waiting_period_days": 30,
            "has_insured_waiver": True,
        },
        "benefits": [
            {"benefit_type": "basic", "benefit_name": "住院医疗", "benefit_amount": "100万", "payment_limit": "按条款"},
            {"benefit_type": "special", "benefit_name": "重疾津贴", "benefit_amount": "2万", "payment_limit": "1次"},
        ],
    }


def test_product_crud_with_chinese_types_and_audit(client, admin_headers):
    created = client.post("/api/products", headers=admin_headers, json=_product_payload())
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "测试医疗产品"
    assert body["type"] == "医疗险"
    assert body["deductible"] == 10000

    detail = client.get(f"/api/products/{body['id']}")
    assert detail.status_code == 200, detail.text
    detail_body = detail.json()
    assert detail_body["rule"]["max_age"] == 60
    assert detail_body["rule"]["job_class_limit"] == 4
    assert len(detail_body["benefits"]) == 2
    assert any(b["benefit_name"] == "住院医疗" for b in detail_body["benefits"])

    updated = client.put(
        f"/api/products/{body['id']}",
        headers=admin_headers,
        json={
            "premium_min": 600,
            "type": "重疾险",
            "rule": {"min_age": 18, "max_age": 65},
            "benefits": [{"benefit_type": "basic", "benefit_name": "重疾保障", "benefit_amount": "50万", "payment_limit": "按条款"}],
        },
    )
    assert updated.status_code == 200, updated.text
    updated_body = updated.json()
    assert updated_body["premium_min"] == 600
    assert updated_body["type"] == "重疾险"

    detail2 = client.get(f"/api/products/{body['id']}")
    detail2_body = detail2.json()
    assert detail2_body["rule"]["min_age"] == 18
    assert detail2_body["rule"]["max_age"] == 65
    assert len(detail2_body["benefits"]) == 1
    assert detail2_body["benefits"][0]["benefit_name"] == "重疾保障"

    deleted = client.delete(f"/api/products/{body['id']}", headers=admin_headers)
    assert deleted.status_code == 200, deleted.text

    db = SessionLocal()
    try:
        product = db.query(Product).filter(Product.id == body["id"]).first()
        assert product.status == 0
        audits = db.query(AuditLog).filter(
            AuditLog.action.in_(["product.create", "product.update", "product.soft_delete"]),
            AuditLog.resource_id == str(body["id"]),
        ).all()
        actions = [a.action for a in audits]
        assert actions == ["product.create", "product.update", "product.soft_delete"]
    finally:
        db.close()


def test_invalid_insurance_type_rejected(client, admin_headers):
    payload = _product_payload(type_value="非法险种")
    response = client.post("/api/products", headers=admin_headers, json=payload)
    assert response.status_code == 422


def test_product_rbac_user_forbidden(client, admin_headers):
    _register(client, "catalog-user@example.com")
    token = _login_token(client, "catalog-user@example.com")
    user_headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/products").status_code == 200
    assert client.post("/api/products", headers=user_headers, json=_product_payload()).status_code == 403
    assert client.put("/api/products/1", headers=user_headers, json={"name": "x"}).status_code == 403
    assert client.delete("/api/products/1", headers=user_headers).status_code == 403
    client.cookies.clear()
    assert client.post("/api/products", json=_product_payload()).status_code == 401


def test_product_without_rule_not_silently_sellable():
    from backend.app.engine.models import UserProfile
    from backend.app.engine.rule_engine import filter_candidate_pool_with_reasons

    db = SessionLocal()
    try:
        with_rule = Product(name="有规则产品", company="C", type="医疗险", status=1, premium_min=100, premium_max=200, sum_insured_max=100)
        without_rule = Product(name="无规则产品", company="C", type="医疗险", status=1, premium_min=100, premium_max=200, sum_insured_max=100)
        inactive = Product(name="停售产品", company="C", type="医疗险", status=0, premium_min=100, premium_max=200, sum_insured_max=100)
        db.add_all([with_rule, without_rule, inactive])
        db.flush()
        db.add(Rule(product_id=with_rule.id, min_age=0, max_age=60, job_class_limit=6, waiting_period_days=90))
        db.commit()

        user = UserProfile(age=30, gender="male", annual_income=200000, job_class=2, life_stage="single", family_burden="none", health_status="standard")
        candidates, rejected = filter_candidate_pool_with_reasons(db, user)
        names = {p.name for p in candidates}
        assert "有规则产品" in names
        assert "无规则产品" not in names
        assert "停售产品" not in names
        reasons = {r["name"]: r["reason_code"] for r in rejected}
        assert reasons.get("无规则产品") == "missing_rule"
        assert reasons.get("停售产品") == "inactive"
    finally:
        db.close()


def test_recommendation_api_skips_missing_rule_and_inactive(client):
    db = SessionLocal()
    try:
        db.add(Product(name="API无规则产品", company="C", type="医疗险", status=1, premium_min=100, premium_max=200, sum_insured_max=100))
        db.add(Product(name="API有规则产品", company="C", type="医疗险", status=1, premium_min=100, premium_max=200, sum_insured_max=100))
        db.flush()
        rule_product = db.query(Product).filter(Product.name == "API有规则产品").first()
        db.add(Rule(product_id=rule_product.id, min_age=0, max_age=60, job_class_limit=6, waiting_period_days=90))
        db.commit()
    finally:
        db.close()

    payload = {
        "age": 30,
        "gender": "male",
        "annual_income": 200000,
        "job_class": 2,
        "life_stage": "single",
        "family_burden": "none",
        "health_status": "standard",
        "health_issues": [],
        "existing_coverage": [],
        "budget_ratio": 0.08,
        "preferred_companies": [],
        "enable_llm_engine": False,
    }
    response = client.post("/api/recommend", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()
    package_names = {p["name"] for pkg in data["packages"] for p in pkg["products"]}
    assert "API无规则产品" not in package_names
    assert any(
        item["name"] == "API无规则产品" and item["reason_code"] == "missing_rule"
        for item in data["not_recommended_details"]
    )
