from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


PRODUCT_TYPES = ["医疗险", "意外险", "重疾险", "定期寿险", "防癌险", "年金险"]
TYPE_ALIASES = {
    "百万医疗": "医疗险",
    "医疗": "医疗险",
    "意外": "意外险",
    "重疾": "重疾险",
    "重大疾病": "重疾险",
    "寿险": "定期寿险",
    "定寿": "定期寿险",
    "防癌": "防癌险",
    "年金": "年金险",
}


class BenefitDraft(BaseModel):
    benefit_type: str = "basic"
    benefit_name: str = ""
    benefit_amount: str = ""
    payment_limit: str = ""


def _normalize_health_requirements(value) -> tuple[Any, bool]:
    """归一化健康要求，返回 (归一化结果, 是否未结构化)。

    dict 仅保留 exclude/caution 两键、元素归一为字符串；list 不静默当作
    caution（引擎对 list 只填 caution），原样保留并打 unstructured 标记
    交发布闸拦截、留人工审核；None 表示页面无法判断，保持 None。
    """
    if value is None:
        return None, False
    if isinstance(value, dict):
        cleaned: dict[str, list[str]] = {}
        for key in ("exclude", "caution"):
            items = value.get(key)
            if isinstance(items, str):
                items = [items]
            if not isinstance(items, list):
                items = []
            cleaned[key] = [str(item).strip() for item in items if str(item).strip()]
        return cleaned, False
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()], True
    return [str(value).strip()], True


class ProductDraftSchema(BaseModel):
    name: str = Field(min_length=1)
    company: str = Field(min_length=1)
    type: Literal["医疗险", "意外险", "重疾险", "定期寿险", "防癌险", "年金险"]
    premium_min: float | None = Field(default=None, ge=0)
    premium_max: float | None = Field(default=None, ge=0)
    sum_insured_min: float | None = Field(default=None, ge=0)
    sum_insured_max: float | None = Field(default=None, ge=0)
    coverage_period: str = ""
    payment_period: str = ""
    source_url: str | None = None
    deductible: float | None = Field(default=None, ge=0)
    disease_count: int | None = Field(default=None, ge=0)
    mild_disease_count: int = Field(default=0, ge=0)
    moderate_disease_count: int = Field(default=0, ge=0)
    has_mild_coverage: bool = False
    has_moderate_coverage: bool = False
    has_multi_claim: bool = False
    # 规则相关字段允许 None（LLM 无法确认时输出 null）：宽松默认值一旦发布
    # 成真实投保规则，会把不可投保产品推荐给不符合条件的用户（INS-001）。
    min_age: int | None = Field(default=None, ge=0, le=120)
    max_age: int | None = Field(default=None, ge=0, le=120)
    job_class_limit: int | None = Field(default=None, ge=1, le=6)
    waiting_period_days: int | None = Field(default=None, ge=0)
    has_insured_waiver: bool | None = None
    has_insurer_waiver: bool | None = None
    health_disclosure_count: int | None = Field(default=None, ge=0)
    health_requirements: Any = None
    health_requirements_unstructured: bool = False
    benefits: list[BenefitDraft] = Field(default_factory=list)

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, value):
        raw = str(value or "").strip()
        if raw in PRODUCT_TYPES:
            return raw
        for key, normalized in TYPE_ALIASES.items():
            if key in raw:
                return normalized
        return "医疗险"

    @field_validator("premium_max", "sum_insured_max")
    @classmethod
    def normalize_max(cls, value):
        # None 表示"页面未披露"，必须保留为 None 而不是归零。
        if value is None:
            return None
        return value or 0

    @model_validator(mode="after")
    def normalize_unknown_rule_defaults(self):
        # 旧提取口径用 0/100/6 填"无法提取"。仍返回这一全默认形态的草稿
        # （如启发式提取器）按"规则字段未知"处理，防止未确认的宽松默认值
        # 被当成真实投保规则自动发布。
        if self.min_age == 0 and self.max_age == 100 and self.job_class_limit == 6:
            self.min_age = None
            self.max_age = None
            self.job_class_limit = None
        return self

    @model_validator(mode="after")
    def normalize_health_requirements(self):
        normalized, unstructured = _normalize_health_requirements(self.health_requirements)
        self.health_requirements = normalized
        self.health_requirements_unstructured = unstructured
        return self


def normalize_and_validate_product(data: dict, base_confidence: float = 0.7) -> tuple[dict, float]:
    prepared = {**data}
    prepared["name"] = prepared.get("name") or "待审核产品"
    prepared["company"] = prepared.get("company") or "待审核"
    prepared["type"] = prepared.get("type") or "医疗险"
    try:
        normalized = ProductDraftSchema.model_validate(prepared).model_dump()
        confidence = base_confidence
    except ValidationError:
        normalized = ProductDraftSchema.model_validate({**prepared, "type": "医疗险"}).model_dump()
        confidence = min(base_confidence, 0.45)

    filled = sum(1 for key in ["name", "company", "type", "premium_min", "sum_insured_max", "source_url"] if normalized.get(key))
    confidence = min(1.0, max(0.1, confidence + filled * 0.03))
    return normalized, confidence
