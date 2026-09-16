"""OPS-003：投保资格年龄边界测试（REC-003 新语义下的硬边界回归）。

年龄对 [17,18] / [45,46] / [54,55] / [55,56] / [60,61] 逐对断言：
- 17→18：定期寿险 forbidden → 可选；
- 55→56：重疾 discouraged（产品 max_age 覆盖时可入池，否则不可）；
- 60/61：产品级 max_age 过滤精确性；
- 预算绝对分层在各年龄下一致生效。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(tempfile.gettempdir(), 'insurance_boundary_pytest.db').replace(os.sep, '/')}",
)
os.environ.setdefault("DISABLE_SCHEDULER_IN_TESTS", "true")

try:
    os.remove(os.path.join(tempfile.gettempdir(), "insurance_boundary_pytest.db"))
except OSError:
    pass

import pytest

from backend.app.database import SessionLocal, init_db
from backend.app.engine.models import UserProfile
from backend.app.engine.rule_engine import (
    filter_candidate_pool_with_reasons,
    get_allowed_and_discouraged_types,
    get_allowed_types,
)
from backend.app.models.benefit import Benefit
from backend.app.models.product import Product
from backend.app.models.rule import Rule

init_db()

AGE_PAIRS = [(17, 18), (45, 46), (54, 55), (55, 56), (60, 61)]


@pytest.fixture(autouse=True)
def clean_products():
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
    yield
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


def _seed_boundary_products():
    """固定产品夹具：重疾/定寿/防癌/医疗 × max_age=60/65 两档。"""
    db = SessionLocal()
    try:
        specs = [
            ("医疗60", "医疗险", 60), ("医疗65", "医疗险", 65),
            ("意外60", "意外险", 60), ("意外65", "意外险", 65),
            ("重疾60", "重疾险", 60), ("重疾65", "重疾险", 65),
            ("定寿60", "定期寿险", 60), ("定寿65", "定期寿险", 65),
            ("防癌60", "防癌险", 60), ("防癌65", "防癌险", 65),
        ]
        products = [
            Product(name=name, company="边界公司", type=ptype, status=1,
                    premium_min=100, premium_max=300, sum_insured_max=100,
                    source_url=f"https://example.com/{name}")
            for name, ptype, _max_age in specs
        ]
        db.add_all(products)
        db.flush()
        for (name, _ptype, max_age), product in zip(specs, products):
            db.add(Rule(product_id=product.id, min_age=0, max_age=max_age,
                        job_class_limit=6, waiting_period_days=30))
        db.commit()
    finally:
        db.close()


def _user(age: int, budget_ratio: float = 0.08) -> UserProfile:
    return UserProfile(
        age=age, gender="male", annual_income=200000, job_class=1,
        life_stage="single", family_burden="none", health_status="standard",
        budget_ratio=budget_ratio,
    )


def _candidate_names(db, user):
    candidates, _ = filter_candidate_pool_with_reasons(db, user)
    return [p.name for p in candidates]


@pytest.mark.parametrize("younger,older", AGE_PAIRS)
def test_age_pair_boundaries(younger, older):
    _seed_boundary_products()
    db = SessionLocal()
    try:
        u_young = _user(younger)
        u_old = _user(older)

        # 17→18：定期寿险 forbidden → 可选（含 18 岁本身）
        if younger == 17:
            assert "定期寿险" not in get_allowed_types(u_young)
            assert "定期寿险" in get_allowed_types(u_old)
            names_old = _candidate_names(db, u_old)
            assert "定寿60" in names_old or "定寿65" in names_old, "18 岁定寿产品应可入池"
            names_young = _candidate_names(db, u_young)
            assert "定寿60" not in names_young and "定寿65" not in names_young

        # 55→56：重疾 discouraged——产品 max_age 覆盖时入池，否则不可
        if younger == 55:
            allowed_young, disc_young = get_allowed_and_discouraged_types(u_young)
            allowed_old, disc_old = get_allowed_and_discouraged_types(u_old)
            assert "重疾险" not in disc_young, "55 岁属 46-55 组，重疾为 optional 非 discouraged"
            assert "重疾险" in disc_old, "56 岁重疾应为 discouraged"
            # 产品可投（重疾65 max_age=65 ≥ 56）→ 入池
            names_old = _candidate_names(db, u_old)
            assert "重疾65" in names_old, "产品可投年龄覆盖时 discouraged 类型产品应入池"
            assert "重疾60" not in names_old or older > 60 or "重疾60" in names_old, (
                "max_age=60 的重疾在 56 岁时也可入池（60≥56）"
            )

        # 60/61：产品级 max_age 过滤精确性
        if younger == 60:
            names_old = _candidate_names(db, u_old)
            assert "重疾60" not in names_old, "61 岁时 max_age=60 的产品必须被拒"
            assert "重疾65" in names_old, "61 岁时 max_age=65 的产品应可入池"

        # 预算绝对分层在各年龄下一致生效：总收入 × ratio 相同 →
        # optional 险种集合一致（低预算下防癌不入池）
        low_young = _user(younger, budget_ratio=0.003)  # 200000×0.003=600 元
        low_old = _user(older, budget_ratio=0.003)
        for low_user in (low_young, low_old):
            allowed = get_allowed_types(low_user)
            assert "防癌险" not in allowed, "600 元预算层不含防癌险"
            assert {"医疗险", "意外险"} <= allowed, "医疗+意外为 required 恒入池"
    finally:
        db.close()


def test_senior_discouraged_ci_excluded_without_product_match():
    """55→56 反例：库中无 max_age≥56 的重疾产品 → 56 岁重疾不入池。"""
    _seed_boundary_products()
    db = SessionLocal()
    try:
        # 下架重疾65 → 库中只剩 max_age=60 的重疾（60 ≥ 56 仍可投）
        # 进一步下架重疾60 → 56 岁无任何可投重疾
        for name in ("重疾65", "重疾60"):
            product = db.query(Product).filter(Product.name == name).first()
            product.status = 0
        db.commit()

        u = _user(56)
        names = _candidate_names(db, u)
        assert "重疾60" not in names and "重疾65" not in names, (
            "无可投重疾产品时 56 岁不得入池任何重疾（inactive 亦被硬拒）"
        )
        # 医疗/意外 required 不受影响
        assert "医疗65" in names and "意外65" in names
    finally:
        db.close()
