from typing import Optional
from pydantic import BaseModel


class ScoreDetail(BaseModel):
    coverage: float = 0
    price: float = 0
    flexibility: float = 0
    waiting: float = 0
    adequacy: float = 0
    waiver: float = 0
    brand: float = 0
    service: float = 0


class ProductItem(BaseModel):
    id: int
    name: str
    company: str
    type: str
    layer: str = "core"
    premium: float
    sum_insured: float
    source_url: str = ""
    score: float
    score_detail: ScoreDetail
    risk_warnings: list[dict] = []
    recommendation_reasons: list[str] = []
    not_recommended_reasons: list[str] = []


class Allocation(BaseModel):
    medical: float
    accident: float
    critical_illness: float
    life: float
    cancer: float = 0


class BudgetAnalysisResponse(BaseModel):
    annual_income: float
    total_budget: float
    allocation: Allocation


class SumInsuredAdviceResponse(BaseModel):
    medical: float
    accident: float
    critical_illness: float
    life: float
    cancer: float = 0


class ComboPackageResponse(BaseModel):
    tag: str
    tag_label: str
    total_premium: float
    budget_ratio: float
    budget_utilization: float = 0
    completeness_score: float = 0
    coverage_gap_notes: list[str] = []
    products: list[ProductItem]


class NotRecommendedSummary(BaseModel):
    reason_code: str = "unknown"
    reason: str
    count: int
    examples: list[dict] = []


class NotRecommendedDetail(BaseModel):
    product_id: int | None = None
    name: str | None = None
    type: str | None = None
    reason_code: str = "unknown"
    reason: str


class AIExplanationResponse(BaseModel):
    selected_product_ids: list[int] = []
    summary: str = ""
    reasoning: list[str] = []
    risk_notes: list[str] = []
    comparison_notes: list[str] = []


class RecommendationResponse(BaseModel):
    user_profile: dict
    budget_analysis: BudgetAnalysisResponse
    sum_insured_advice: SumInsuredAdviceResponse
    packages: list[ComboPackageResponse] = []
    llm_narrative: Optional[str] = None
    ai_explanation: Optional[AIExplanationResponse] = None
    engine_mode: str = "rule"
    hard_rule_summary: list[str] = []
    coverage_gap_summary: list[str] = []
    not_recommended_summary: list[NotRecommendedSummary] = []
    not_recommended_details: list[NotRecommendedDetail] = []
    disclaimer: str = "本方案由算法生成，仅供参考，最终承保以保险公司官方条款为准"
