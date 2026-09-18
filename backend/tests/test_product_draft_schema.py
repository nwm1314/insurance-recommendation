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

# DEV-008：与其它测试文件保持一致，先删除上次运行残留的库文件。否则旧库可能停在
# 过期的 Alembic 版本上，使 verify_schema_integrity() 在导入期直接报错。
try:
    os.remove(os.path.join(tempfile.gettempdir(), "insurance_draft_schema_pytest.db"))
except OSError:
    pass

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


# ------------------------------------------------------------ INS-002

def test_health_requirements_dict_kept_and_cleaned():
    normalized, _ = normalize_and_validate_product(_base(
        health_requirements={"exclude": ["高血压", 3], "caution": [" 甲状腺结节 "], "unknown_key": ["x"]}
    ))
    assert normalized["health_requirements"] == {"exclude": ["高血压", "3"], "caution": ["甲状腺结节"]}
    assert normalized["health_requirements_unstructured"] is False


def test_health_requirements_list_flagged_unstructured():
    normalized, _ = normalize_and_validate_product(_base(health_requirements=["甲状腺结节", "高血压"]))
    assert normalized["health_requirements"] == ["甲状腺结节", "高血压"]
    assert normalized["health_requirements_unstructured"] is True


def test_health_requirements_none_and_explicit_empty():
    normalized, _ = normalize_and_validate_product(_base(health_requirements=None))
    assert normalized["health_requirements"] is None
    assert normalized["health_requirements_unstructured"] is False

    normalized, _ = normalize_and_validate_product(_base(health_requirements={"exclude": [], "caution": []}))
    assert normalized["health_requirements"] == {"exclude": [], "caution": []}
    assert normalized["health_requirements_unstructured"] is False


# ------------------------------------------------------------ INS-003

def test_sum_insured_yuan_misreport_normalized_to_wan():
    """按"元"误报的保额（>10000 万）自动 ÷10000 并打标。"""
    normalized, _ = normalize_and_validate_product(_base(sum_insured_min=2000000, sum_insured_max=3000000))
    assert normalized["sum_insured_min"] == 200
    assert normalized["sum_insured_max"] == 300
    assert normalized["sum_insured_unit_normalized"] is True


def test_sum_insured_wan_values_untouched():
    normalized, _ = normalize_and_validate_product(_base(sum_insured_min=5, sum_insured_max=300))
    assert normalized["sum_insured_min"] == 5
    assert normalized["sum_insured_max"] == 300
    assert normalized["sum_insured_unit_normalized"] is False


# ------------------------------------------------------------ DATA-004

def test_type_aliases_resolve_known_names():
    assert normalize_and_validate_product(_base(type="定寿"))[0]["type"] == "定期寿险"
    assert normalize_and_validate_product(_base(type="重疾"))[0]["type"] == "重疾险"
    assert normalize_and_validate_product(_base(type="百万医疗"))[0]["type"] == "医疗险"


def test_type_unknown_names_become_none_not_medical():
    """泛化险种名（终身寿险/两全）与未知文本不再误分，保持 None 留人工。"""
    for unknown in ("终身寿险", "两全保险", "万能险", "至尊保终身计划"):
        normalized, _ = normalize_and_validate_product(_base(type=unknown))
        assert normalized["type"] is None, f"{unknown} 不应被归类为 {normalized['type']}"


def test_type_missing_becomes_none_not_medical():
    """type 缺失不再兜底"医疗险"。"""
    data = _base()
    data.pop("type")
    normalized, _ = normalize_and_validate_product(data)
    assert normalized["type"] is None


def test_type_none_keeps_low_confidence():
    """type 未知时 filled 计数不含 type，confidence 不上浮。"""
    data = _base()
    data.pop("type")
    normalized, confidence = normalize_and_validate_product(data, base_confidence=0.7)
    assert normalized["type"] is None
    # 6 个 filled 维度只剩 name/company/premium_min/sum_insured_max/source_url（缺 type）
    assert confidence < 0.9
