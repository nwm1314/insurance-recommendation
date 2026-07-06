from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator


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


class ProductDraftSchema(BaseModel):
    name: str = Field(min_length=1)
    company: str = Field(min_length=1)
    type: Literal["医疗险", "意外险", "重疾险", "定期寿险", "防癌险", "年金险"]
    premium_min: float = Field(default=0, ge=0)
    premium_max: float = Field(default=0, ge=0)
    sum_insured_min: float = Field(default=0, ge=0)
    sum_insured_max: float = Field(default=0, ge=0)
    coverage_period: str = ""
    payment_period: str = ""
    source_url: str | None = None
    disease_count: int = Field(default=0, ge=0)
    mild_disease_count: int = Field(default=0, ge=0)
    moderate_disease_count: int = Field(default=0, ge=0)
    has_mild_coverage: bool = False
    has_moderate_coverage: bool = False
    has_multi_claim: bool = False
    min_age: int = Field(default=0, ge=0, le=120)
    max_age: int = Field(default=100, ge=0, le=120)
    job_class_limit: int = Field(default=6, ge=1, le=6)
    waiting_period_days: int = Field(default=90, ge=0)
    has_insured_waiver: bool = False
    has_insurer_waiver: bool = False
    health_disclosure_count: int = Field(default=0, ge=0)
    health_requirements: list[Any] = Field(default_factory=list)
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
        return value or 0


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
