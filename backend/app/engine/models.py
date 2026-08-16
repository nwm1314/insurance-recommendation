from dataclasses import dataclass, field
from typing import Optional


@dataclass
class UserProfile:
    age: int
    gender: str
    annual_income: float
    job_class: int
    life_stage: str          # single / married / married_with_kids / empty_nest / retired
    family_burden: str       # none / parents / children / dual
    health_status: str        # standard / substandard / history
    health_issues: list[str] = field(default_factory=list)
    existing_coverage: list[str] = field(default_factory=list)
    budget_ratio: float = 0.08
    preferred_type: Optional[str] = None
    preferred_companies: list[str] = field(default_factory=list)
    enable_llm_engine: bool = False


@dataclass
class ScoredProduct:
    product_id: int
    name: str
    company: str
    type: str
    premium: float
    premium_max: float | None = None
    deductible: float | None = None
    sum_insured: float = 0.0
    source_url: str = ""
    # 链接语义：official=承保公司官网（含演示目录），aggregator=聚合站产品详情页
    source_type: str = ""
    # 交叉验证标注（TASK-035，仅展示不参与决策）
    official_verified: bool = False
    dual_source_verified: bool = False
    third_party_review_url: str | None = None
    third_party_review_title: str | None = None
    layer: str = "core"        # basic / core / supplement
    score: float = 0.0
    score_detail: dict[str, float] = field(default_factory=dict)
    risk_warnings: list[dict] = field(default_factory=list)
    recommendation_reasons: list[str] = field(default_factory=list)
    not_recommended_reasons: list[str] = field(default_factory=list)


@dataclass
class ComboPackage:
    tag: str                   # budget / star / premium
    tag_label: str
    total_premium: float
    total_premium_max: float | None = None
    budget_ratio: float = 0.0
    budget_utilization: float = 0.0
    completeness_score: float = 0.0
    coverage_gap_notes: list[str] = field(default_factory=list)
    products: list[ScoredProduct] = field(default_factory=list)


@dataclass
class BudgetAnalysis:
    annual_income: float
    total_budget: float
    allocation: dict[str, float] = field(default_factory=dict)


@dataclass
class SumInsuredAdvice:
    medical: float
    accident: float
    critical_illness: float
    life: float
    cancer: float = 100000


@dataclass
class RecommendationResult:
    user_profile: dict
    budget_analysis: BudgetAnalysis
    sum_insured_advice: SumInsuredAdvice
    packages: list[ComboPackage] = field(default_factory=list)
    llm_narrative: Optional[str] = None
    engine_mode: str = "rule"
    disclaimer: str = "本方案由算法生成，仅供参考，最终承保以保险公司官方条款为准"
