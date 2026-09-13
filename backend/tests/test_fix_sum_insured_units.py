"""INS-003 回归：一次性保额单位修复脚本（backend/scripts/fix_sum_insured_units.py）。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(tempfile.gettempdir(), 'insurance_fix_units_pytest.db').replace(os.sep, '/')}",
)
os.environ.setdefault("DISABLE_SCHEDULER_IN_TESTS", "true")

try:
    os.remove(os.path.join(tempfile.gettempdir(), "insurance_fix_units_pytest.db"))
except OSError:
    pass

import pytest

from backend.app.database import SessionLocal, init_db

init_db()

from backend.app.models.auth import AuditLog
from backend.app.models.benefit import Benefit
from backend.app.models.data_ingestion import ProductVersion, SourcePlatform
from backend.app.models.product import Product
from backend.app.models.rule import Rule


@pytest.fixture(autouse=True)
def _clean_db():
    db = SessionLocal()
    try:
        for model in (ProductVersion, AuditLog, Benefit, Rule, Product):
            db.query(model).delete()
        db.commit()
    finally:
        db.close()
    yield
    db = SessionLocal()
    try:
        for model in (ProductVersion, AuditLog, Benefit, Rule, Product):
            db.query(model).delete()
        db.commit()
    finally:
        db.close()


def _make_ingested_product(name: str, sum_insured_max) -> int:
    """经摄取发布的产品（有 ProductVersion 记录）。"""
    db = SessionLocal()
    try:
        platform = db.query(SourcePlatform).order_by(SourcePlatform.id).first()
        product = Product(
            name=name, company="测试公司", type="医疗险", status=1,
            premium_min=500, premium_max=800, sum_insured_max=sum_insured_max,
        )
        db.add(product)
        db.flush()
        db.add(ProductVersion(product_id=product.id, product_draft_id=0, version_data={"name": name}, published_by=None))
        db.commit()
        return product.id
    finally:
        db.close()


def _make_seed_product(name: str, sum_insured_max) -> int:
    """种子产品（无 ProductVersion 记录）。"""
    db = SessionLocal()
    try:
        product = Product(
            name=name, company="种子公司", type="医疗险", status=1,
            premium_min=500, premium_max=800, sum_insured_max=sum_insured_max,
        )
        db.add(product)
        db.commit()
        return product.id
    finally:
        db.close()


def _run_fixer(monkeypatch, *argv: str) -> int:
    import backend.scripts.fix_sum_insured_units as fixer

    monkeypatch.setattr(sys, "argv", ["fix_sum_insured_units.py", *argv])
    return fixer.main()


def test_fix_divides_yuan_misreport_for_ingested_products(monkeypatch):
    ingested_id = _make_ingested_product("元误报产品", 3000000)
    seed_id = _make_seed_product("种子产品", 3000000)

    assert _run_fixer(monkeypatch) == 0

    db = SessionLocal()
    try:
        ingested = db.query(Product).filter(Product.id == ingested_id).first()
        assert ingested.sum_insured_max == 300, "ingested product must be divided by 10000"
        seed = db.query(Product).filter(Product.id == seed_id).first()
        assert seed.sum_insured_max == 3000000, "seed products must not be touched"
        audit = db.query(AuditLog).filter(AuditLog.action == "data.fix_sum_insured_units").all()
        assert len(audit) == 1
        assert audit[0].resource_id == str(ingested_id)
        assert audit[0].detail["sum_insured_max"] == {"before": 3000000, "after": 300}
    finally:
        db.close()


def test_fix_dry_run_writes_nothing(monkeypatch):
    ingested_id = _make_ingested_product("干跑产品", 3000000)

    assert _run_fixer(monkeypatch, "--dry-run") == 0

    db = SessionLocal()
    try:
        product = db.query(Product).filter(Product.id == ingested_id).first()
        assert product.sum_insured_max == 3000000, "dry-run must not write to the database"
        assert db.query(AuditLog).count() == 0
    finally:
        db.close()
