from typing import Optional
from pydantic import BaseModel


class ScoreDetail(BaseModel):
    coverage: float = 0
    price: float = 0
    flexibility: float = 0
    waiting: float = 0
    adequacy: float = 0
    waiver: float = 0


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


class Allocation(BaseModel):
    medical: float
    accident: float
    critical_illness: float
    life: float


class BudgetAnalysisResponse(BaseModel):
    annual_income: float
    total_budget: float
    allocation: Allocation


class SumInsuredAdviceResponse(BaseModel):
    medical: float
    accident: float
    critical_illness: float
    life: float


class ComboPackageResponse(BaseModel):
    tag: str
    tag_label: str
    total_premium: float
    budget_ratio: float
    products: list[ProductItem]


class RecommendationResponse(BaseModel):
    user_profile: dict
    budget_analysis: BudgetAnalysisResponse
    sum_insured_advice: SumInsuredAdviceResponse
    packages: list[ComboPackageResponse] = []
    llm_narrative: Optional[str] = None
    engine_mode: str = "rule"
    disclaimer: str = "本方案由算法生成，仅供参考，最终承保以保险公司官方条款为准"
