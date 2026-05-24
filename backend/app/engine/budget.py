from backend.app.engine.models import UserProfile, BudgetAnalysis, SumInsuredAdvice
from backend.app.config import BUDGET_RULES


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
                allocation=tier["allocation"],
            )
    # fallback
    return BudgetAnalysis(
        annual_income=income,
        total_budget=round(income * 0.08, 2),
        allocation={"medical": 0.15, "accident": 0.15, "critical_illness": 0.45, "life": 0.25},
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
