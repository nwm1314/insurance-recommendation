from backend.app.engine.models import UserProfile, ScoredProduct, ComboPackage, BudgetAnalysis
from backend.app.engine.rule_engine import get_allowed_types
from backend.app.config import SCORING_WEIGHTS

# Insurance type to layer mapping
LAYER_MAP = {
    "医疗险": "basic", "意外险": "basic",
    "重疾险": "core", "定期寿险": "core",
    "防癌险": "supplement", "年金险": "supplement",
}

# Package definitions: tag → (label, budget_multiplier, sort_strategy)
# - "cheapest": sort by premium ascending, pick lowest price
# - "best_score": sort by raw score descending (with tier preference bonus)
PACKAGE_DEFS = [
    ("budget", "🛡 极致性价比", 0.5, "cheapest"),
    ("star", "⭐ 全面保障", 0.8, "best_score"),
    ("premium", "👑 尊享无忧", 1.0, "best_score"),
]


def _get_tier_preference(user: UserProfile) -> dict[int, float]:
    """Calculate company tier weight multipliers based on user profile.
    Returns {tier: weight_multiplier} where 1.0 is neutral.
    These are small tiebreaker weights, not dominant factors."""
    prefs = {1: 1.0, 2: 1.0, 3: 1.0}
    tier_cfg = SCORING_WEIGHTS.get("user_tier_preference", {})

    # Company preference: give a substantial bonus to preferred companies
    if user.preferred_companies:
        for tier in [1, 2, 3]:
            prefs[tier] += 0.08

    # Income: high earners prefer T1 (brand trust)
    if user.annual_income >= tier_cfg.get("high_income_threshold", 300000):
        prefs[int(tier_cfg.get("high_income_tier", 1))] += 0.03

    # Health issues: prefer T2 (flexible underwriting)
    if user.health_status != "standard" and user.health_issues:
        prefs[int(tier_cfg.get("health_issue_tier", 2))] += 0.05

    # Budget sensitive: prefer T3 (affordability)
    if user.budget_ratio <= tier_cfg.get("budget_threshold", 0.06):
        prefs[int(tier_cfg.get("budget_tier", 3))] += 0.03

    # Age: young users prefer T3 (internet-native), older prefer T1/T2
    if user.age < tier_cfg.get("age_young_threshold", 30):
        prefs[int(tier_cfg.get("age_young_tier", 3))] += 0.03
    elif user.age > tier_cfg.get("age_senior_threshold", 45):
        senior_tier = int(tier_cfg.get("age_senior_tier", 1))
        prefs[senior_tier] += 0.03
        prefs[2] += 0.03  # T2 also gets preference for older users

    return prefs


def build_combos(
    scored_products: list[dict],
    user: UserProfile,
    budget: BudgetAnalysis,
) -> list[ComboPackage]:
    allowed_types = get_allowed_types(user)

    # Group products by type, with a copy for each package to avoid mutation
    products_by_type: dict[str, list[dict]] = {}
    for p in scored_products:
        ptype = p.get("type", "")
        if ptype not in products_by_type:
            products_by_type[ptype] = []
        products_by_type[ptype].append(p)

    combos = []
    for tag, label, budget_mult, strategy in PACKAGE_DEFS:
        combo = _build_single_combo(products_by_type, allowed_types, budget, tag, label, strategy, user)
        if combo.products:
            combos.append(combo)
    return combos


def _build_single_combo(
    products_by_type: dict[str, list[dict]],
    allowed_types: set[str],
    budget: BudgetAnalysis,
    tag: str,
    label: str,
    strategy: str,
    user: UserProfile,
) -> ComboPackage:
    max_spend = budget.total_budget * {
        "budget": 0.5, "star": 0.8, "premium": 1.0,
    }.get(tag, 0.8)

    # Sort a fresh copy per type based on strategy, with tier preference bonus
    tier_prefs = _get_tier_preference(user)
    preferred = set(user.preferred_companies) if user.preferred_companies else set()
    sorted_pools: dict[str, list[dict]] = {}
    for ins_type, plist in products_by_type.items():
        copied = list(plist)
        if strategy == "cheapest":
            copied.sort(key=lambda x: x.get("premium", float("inf")))
        elif strategy == "best_value":
            copied.sort(key=lambda x: x.get("score", 0) / max(x.get("premium", 1), 1), reverse=True)
        else:  # best_score: apply tier preference + company preference as score multiplier
            def tier_adjusted_score(p):
                base = p.get("score", 0)
                tier = p.get("company_tier", 2)
                bonus = tier_prefs.get(tier, 1.0)
                # Extra bump for explicitly preferred companies
                if preferred and p.get("company", "") in preferred:
                    bonus += 0.12
                return base * bonus
            copied.sort(key=tier_adjusted_score, reverse=True)
        sorted_pools[ins_type] = copied

    # Build type_order dynamically based on allowed_types and package tier
    core_types = ["医疗险", "意外险"]
    critical_types = ["重疾险"]  # primary critical illness
    fallback_critical = "防癌险"  # secondary (age 56+ replacement)
    life_types = ["定期寿险"]

    type_order: list[str] = []

    # Always include core types if allowed
    for t in core_types:
        if t in allowed_types:
            type_order.append(t)

    # Critical illness: use primary if allowed, else fallback
    has_critical = any(t in allowed_types for t in critical_types)
    if has_critical:
        type_order.extend(t for t in critical_types if t in allowed_types)
    elif fallback_critical in allowed_types:
        type_order.append(fallback_critical)

    # Life insurance: budget skips, star/premium adds
    if tag != "budget":
        type_order.extend(t for t in life_types if t in allowed_types)

    # Premium: also add supplementary types
    if tag == "premium":
        for t in [fallback_critical]:
            if t in allowed_types and t not in type_order:
                type_order.append(t)

    scored_list: list[ScoredProduct] = []
    total = 0.0
    total_max = 0.0
    unknown_max = False
    picked_ids: set[int] = set()

    for ins_type in type_order:
        if ins_type not in allowed_types:
            continue
        candidates = sorted_pools.get(ins_type, [])
        # Skip already-picked products (for types with only 1 product shared across)
        available = [c for c in candidates if c.get("product_id") not in picked_ids]
        if not available:
            continue

        best = available[0]
        premium_max = best.get("premium_max")
        # The API represents a missing premium_min as 0. If an upper quote
        # bound is available, use it as the conservative lower-bound display
        # value instead of presenting a misleading zero-premium plan.
        premium = best.get("premium", 0) or 0
        if premium <= 0 and premium_max is not None and premium_max > 0:
            premium = premium_max
        # Entry check: the plan's lowest total must fit the spend limit.
        if total + premium > max_spend:
            continue
        # Max check: the plan's highest total must never exceed the spend limit
        # (products without a disclosed upper bound are allowed with a
        # "以核保为准" mark, since their max cannot be verified).
        if premium_max is not None and total_max + premium_max > max_spend:
            continue

        total += premium
        total_max += premium_max if premium_max is not None else 0
        unknown_max = unknown_max or premium_max is None
        picked_ids.add(best.get("product_id", 0))
        scored_list.append(ScoredProduct(
            product_id=best.get("product_id", 0),
            name=best.get("name", ""),
            company=best.get("company", ""),
            type=ins_type,
            premium=premium,
            premium_max=premium_max,
            deductible=best.get("deductible"),
            sum_insured=best.get("sum_insured", 0),
            source_url=best.get("source_url", ""),
            source_type=best.get("source_type", ""),
            layer=LAYER_MAP.get(ins_type, "core"),
            score=best.get("score", 0),
            score_detail=best.get("score_detail", {}),
            risk_warnings=best.get("risk_warnings", []),
            recommendation_reasons=best.get("recommendation_reasons") or [],
            not_recommended_reasons=best.get("not_recommended_reasons") or [],
        ))

    ratio = total / budget.annual_income if budget.annual_income > 0 else 0
    covered_types = {p.type for p in scored_list}
    required_types = _required_types_for_package(allowed_types, tag)
    missing_types = [t for t in required_types if t not in covered_types]
    completeness = 1.0 if not required_types else (len(required_types) - len(missing_types)) / len(required_types)
    budget_utilization = total / max(max_spend, 1)

    # Premium: add second-best products within remaining budget for extra coverage
    if tag == "premium":
        for ins_type in type_order:
            if ins_type not in allowed_types:
                continue
            candidates = sorted_pools.get(ins_type, [])
            remaining = [c for c in candidates if c.get("product_id") not in picked_ids]
            if not remaining:
                continue
            extra = remaining[0]
            extra_max = extra.get("premium_max")
            extra_premium = extra.get("premium", 0) or 0
            if extra_premium <= 0 and extra_max is not None and extra_max > 0:
                extra_premium = extra_max
            if total + extra_premium > max_spend:
                continue
            if extra_max is not None and total_max + extra_max > max_spend:
                continue
            total += extra_premium
            total_max += extra_max if extra_max is not None else 0
            unknown_max = unknown_max or extra_max is None
            picked_ids.add(extra.get("product_id", 0))
            scored_list.append(ScoredProduct(
                product_id=extra.get("product_id", 0),
                name=extra.get("name", ""),
                company=extra.get("company", ""),
                type=ins_type,
                premium=extra_premium,
                premium_max=extra_max,
                deductible=extra.get("deductible"),
                sum_insured=extra.get("sum_insured", 0),
                source_url=extra.get("source_url", ""),
                source_type=extra.get("source_type", ""),
                layer="supplement",
                score=extra.get("score", 0),
                score_detail=extra.get("score_detail", {}),
                risk_warnings=extra.get("risk_warnings", []),
                recommendation_reasons=extra.get("recommendation_reasons") or [],
                not_recommended_reasons=extra.get("not_recommended_reasons") or [],
            ))

    ratio = total / budget.annual_income if budget.annual_income > 0 else 0
    covered_types = {p.type for p in scored_list}
    missing_types = [t for t in required_types if t not in covered_types]
    completeness = 1.0 if not required_types else (len(required_types) - len(missing_types)) / len(required_types)
    budget_utilization = total / max(max_spend, 1)
    # When any included product has no disclosed upper bound, the plan's max
    # total is not verifiable — expose the lower bound only and mark
    # total_premium_max as None so the UI shows "起 / 以核保为准".
    total_premium_max = round(total_max, 2) if total_max > 0 and not unknown_max else None
    return ComboPackage(
        tag=tag,
        tag_label=label,
        total_premium=round(total, 2),
        total_premium_max=total_premium_max,
        budget_ratio=round(ratio, 4),
        budget_utilization=round(min(budget_utilization, 1.0), 4),
        completeness_score=round(max(completeness, 0.0), 4),
        coverage_gap_notes=[f"预算或候选池限制，暂未配置{t}" for t in missing_types],
        products=scored_list,
    )


def _required_types_for_package(allowed_types: set[str], tag: str) -> list[str]:
    required = [t for t in ["医疗险", "意外险"] if t in allowed_types]
    if "重疾险" in allowed_types:
        required.append("重疾险")
    elif "防癌险" in allowed_types:
        required.append("防癌险")
    if tag != "budget" and "定期寿险" in allowed_types:
        required.append("定期寿险")
    return required
