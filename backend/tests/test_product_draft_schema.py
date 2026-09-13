"""INS-001/002/003 回归：产品草稿 schema 的宽松默认值、健康要求结构与保额单位防呆。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(tempfile.gettempdir(), 'insurance_draft_schema_pytest.db').replace(os.sep, '/')}",
)
os.environ.setdefault("DISABLE_SCHEDULER_IN_TESTS", "true")

from backend.app.data_ingestion.validators.product_schema import (
    ProductDraftSchema,
    normalize_and_validate_product,
)


def _base(**overrides) -> dict:
    data = {
        "name": "测试产品",
        "company": "测试公司",
        "type": "医疗险",
        "premium_min": 300,
        "premium_max": 600,
        "sum_insured_max": 300,
        "source_url": "https://example.com/p",
        "min_age": 28,
        "max_age": 60,
        "job_class_limit": 1,
        "waiting_period_days": 30,
        "health_requirements": {"exclude": ["高血压"], "caution": []},
    }
    data.update(overrides)
    return data


# ------------------------------------------------------------ INS-001

def test_rule_fields_accept_null_and_drop_defaults():
    normalized, _ = normalize_and_validate_product(_base(min_age=None, max_age=None, job_class_limit=None))
    assert normalized["min_age"] is None
    assert normalized["max_age"] is None
    assert normalized["job_class_limit"] is None

    # 缺省（未提供）同样归一为 None，而不是宽松默认值
    data = _base()
    for key in ("min_age", "max_age", "job_class_limit", "waiting_period_days", "health_requirements"):
        data.pop(key)
    normalized, _ = normalize_and_validate_product(data)
    assert normalized["min_age"] is None
    assert normalized["waiting_period_days"] is None
    assert normalized["health_requirements"] is None


def test_legacy_full_default_signature_normalizes_to_unknown():
    """旧口径"全默认值形态"（0/100/6）按规则字段未知处理，不得保留为真实规则。"""
    normalized, _ = normalize_and_validate_product(_base(min_age=0, max_age=100, job_class_limit=6))
    assert normalized["min_age"] is None
    assert normalized["max_age"] is None
    assert normalized["job_class_limit"] is None


def test_real_boundary_values_are_preserved():
    """单点默认值（如新生儿 min_age=0）只要不是三要素全默认形态就保留。"""
    normalized, _ = normalize_and_validate_product(_base(min_age=0, max_age=60, job_class_limit=6))
    assert normalized["min_age"] == 0
    assert normalized["max_age"] == 60
    assert normalized["job_class_limit"] == 6


def test_heuristic_full_defaults_still_validate():
    """启发式提取器返回全量默认值，schema 必须兼容（归一为规则字段未知）。"""
    heuristic = {
        "name": "待审核产品", "company": "待审核", "type": "医疗险",
        "premium_min": 0, "premium_max": 0, "sum_insured_min": 0, "sum_insured_max": 0,
        "min_age": 0, "max_age": 100, "job_class_limit": 6, "waiting_period_days": 90,
        "health_requirements": [], "benefits": [],
    }
    normalized, confidence = normalize_and_validate_product(heuristic, base_confidence=0.35)
    assert normalized["min_age"] is None and normalized["max_age"] is None
    assert normalized["waiting_period_days"] == 90
    assert confidence < 0.8


def test_premium_and_deductible_none_preserved():
    normalized, _ = normalize_and_validate_product(_base(premium_min=None, premium_max=None, deductible=10000))
    assert normalized["premium_min"] is None
    assert normalized["premium_max"] is None
    assert normalized["deductible"] == 10000
