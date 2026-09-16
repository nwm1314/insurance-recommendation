from backend.app.engine.models import UserProfile, BudgetAnalysis, SumInsuredAdvice
from backend.app.config import BUDGET_RULES


DEFAULT_ALLOCATION = {"medical": 0.15, "accident": 0.15, "critical_illness": 0.40, "life": 0.25, "cancer": 0.05}


def _normalize_allocation(allocation: dict) -> dict[str, float]:
    normalized = {**DEFAULT_ALLOCATION, **(allocation or {})}
    total = sum(normalized.values())
    if total <= 0:
        return DEFAULT_ALLOCATION
    return {key: round(value / total, 4) for key, value in normalized.items()}


def calculate_budget(user: UserProfile) -> BudgetAnalysis:
    """Calculate total budget and allocation by income tier"""
    income = user.annual_income
    tiers = BUDGET_RULES.get("income_tiers", [])
    for tier in tiers:
        if income <= tier["max_income"]:
            total_budget = income * user.budget_ratio
            return BudgetAnalysis(
                annual_income=income,
                total_budget=round(total_budget, 2),
                allocation=_normalize_allocation(tier["allocation"]),
            )
    # fallback
    return BudgetAnalysis(
        annual_income=income,
        total_budget=round(income * 0.08, 2),
        allocation=DEFAULT_ALLOCATION,
    )


def calculate_sum_insured(user: UserProfile) -> SumInsuredAdvice:
    """Calculate suggested sum insured for each insurance type"""
    income = user.annual_income
    config = BUDGET_RULES.get("sum_insured", {})
    is_breadwinner = user.life_stage in ("married_with_kids", "married") and user.family_burden in ("children", "dual")
    life_mult = config.get("life_multiplier", 5)

    medical = config.get("medical", 3000000)
    accident = income * config.get("accident_multiplier", 8)
    ci = min(
        income * config.get("critical_illness_multiplier", 3) + config.get("critical_illness_base", 300000),
        config.get("critical_illness_max", 1000000),
    )
    life = max(income * life_mult, config.get("life_min", 500000))
    if is_breadwinner:
        life *= 2

    return SumInsuredAdvice(
        medical=round(medical),
        accident=round(accident),
        critical_illness=round(ci),
        life=round(life),
        cancer=config.get("cancer_default", 150000),
    )


def calculate_coverage_gaps(user: UserProfile, advice: SumInsuredAdvice) -> dict[str, dict]:
    """已有保单参与缺口分析（REC-001，仅软层展示，不硬性排除）。

    返回 {险种: {"suggested": 建议保额(元), "existing": 同险种已有保额合计(元),
    "gap": max(0, suggested - existing)}}。未披露保额（null）按 0 计入，
    gap 不会为负——已有保额超出建议时不产生"负缺口"。
    """
    suggested_map = {
        "医疗险": advice.medical,
        "意外险": advice.accident,
        "重疾险": advice.critical_illness,
        "定期寿险": advice.life,
        "防癌险": advice.cancer,
    }
    existing_by_type: dict[str, float] = {}
    for policy in user.existing_policies or []:
        if not isinstance(policy, dict):
            continue
        policy_type = (policy.get("type") or "").strip()
        if not policy_type:
            continue
        amount = policy.get("sum_insured") or 0
        existing_by_type[policy_type] = existing_by_type.get(policy_type, 0) + amount
    return {
        insurance_type: {
            "suggested": suggested,
            "existing": round(existing_by_type.get(insurance_type, 0)),
            "gap": round(max(0, suggested - existing_by_type.get(insurance_type, 0))),
        }
        for insurance_type, suggested in suggested_map.items()
    }
