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
    sum_insured: float
    source_url: str = ""
    layer: str = "core"        # basic / core / supplement
    score: float = 0.0
    score_detail: dict[str, float] = field(default_factory=dict)
    risk_warnings: list[dict] = field(default_factory=list)


@dataclass
class ComboPackage:
    tag: str                   # budget / star / premium
    tag_label: str
    total_premium: float
    budget_ratio: float
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
