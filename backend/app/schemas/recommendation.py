"""POST /api/recommend 响应模型（OPS-004）。

字段清单逐一核对 `_build_response`（backend/app/api/recommend.py）与前端
消费契约（frontend/src/types/index.ts）。response_model 会剥离未声明字段，
新增响应键时必须同步此处。
"""
from typing import Optional
from pydantic import BaseModel, Field


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
    premium_max: Optional[float] = None
    deductible: Optional[float] = None
    sum_insured: float
    # REC-002：价格口径说明与是否披露报价
    premium_basis_note: Optional[str] = None
    premium_known: bool = True
    source_url: str = ""
    # official=承保公司官网，aggregator=聚合站产品详情页
    source_type: str = ""
    official_verified: bool = False
    dual_source_verified: bool = False
    third_party_review_url: Optional[str] = None
    third_party_review_title: Optional[str] = None
    last_verified_at: Optional[str] = None
    data_stale: bool = False
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
    # REC-001：无社保身份的医疗险建议提示（有社保/未填时为 null）
    medical_social_note: Optional[str] = None


class PackageCoverageGap(BaseModel):
    type: str
    suggested: float
    covered: float
    gap: float
    note: Optional[str] = None


class ComboPackageResponse(BaseModel):
    tag: str
    tag_label: str
    total_premium: float
    total_premium_max: Optional[float] = None
    budget_ratio: float
    budget_utilization: float = 0
    completeness_score: float = 0
    coverage_gap_notes: list[str] = []
    products: list[ProductItem]
    # REC-004：按 required 险种的保额缺口（单位元）
    coverage_gaps: list[PackageCoverageGap] = []


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
    # DATA-002：复现元数据（engine/rule/scoring 版本与权重 hash）
    meta: dict = Field(default_factory=dict)
    hard_rule_summary: list[str] = []
    coverage_gap_summary: list[str] = []
    not_recommended_summary: list[NotRecommendedSummary] = []
    not_recommended_details: list[NotRecommendedDetail] = []
    # TASK-029：画像评估（历史记录可能缺省）
    profile_assessment: Optional[dict] = None
    # REC-001：按险种的保额缺口 {"险种": {"suggested","existing","gap"}}（元）
    coverage_gaps: dict = Field(default_factory=dict)
    # AI-002：缓存命中标注（仅 AI 模式成功路径出现）
    ai_from_cache: Optional[bool] = None
    disclaimer: str = "本方案由算法生成，仅供参考，最终承保以保险公司官方条款为准"
