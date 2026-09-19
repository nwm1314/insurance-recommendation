from backend.app.engine.models import UserProfile, ScoredProduct, ComboPackage, BudgetAnalysis, SumInsuredAdvice
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
#
# OPEN-003（方案 2）：套餐名改为**中性功能化**表述，不再使用"极致性价比 /
# 全面保障 / 尊享无忧"。原因：旧名中的"尊享""全面"隐含"越贵越好"的优劣暗示，
# 而三套方案的真实差异只是**预算档位与保障完整度**（budget_multiplier 0.5/0.8/1.0
# 以及 star/premium 会做一次缺失险种置换，见 _required_types_for_package），
# 并不存在"哪个更好"。新名直接说明取向，避免诱导超预算选择。
PACKAGE_DEFS = [
    ("budget", "🛡 低保费优先", 0.5, "cheapest"),
    ("star", "⭐ 均衡配置", 0.8, "best_score"),
    ("premium", "👑 高保额优先", 1.0, "best_score"),
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
    sum_insured_advice: SumInsuredAdvice,
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
        combo = _build_single_combo(products_by_type, allowed_types, budget, tag, label, strategy, user, sum_insured_advice)
        if combo.products:
            combos.append(combo)
    return combos


def _swap_in_missing_required(
    scored_list: list[ScoredProduct],
    sorted_pools: dict[str, list[dict]],
    picked_ids: set[int],
    required_types: list[str],
    missing_types: list[str],
    total: float,
    total_max: float,
    unknown_max: bool,
    max_spend: float,
) -> tuple[float, float, bool, bool]:
    """REC-004 一次置换 pass：用缺失 required 类型中最便宜的合格产品替换
    已选里分值最低且非医疗/意外的产品，仅当替换后 completeness 提升时
    采纳（否则原样返回）。budget 套餐不调用本函数。

    Returns (total, total_max, unknown_max, swapped)。
    """
    if not missing_types:
        return total, total_max, unknown_max, False

    swappable = [p for p in scored_list if p.type not in ("医疗险", "意外险")]
    if not swappable:
        return total, total_max, unknown_max, False

    target_type = missing_types[0]
    candidates = [
        c for c in sorted_pools.get(target_type, [])
        if c.get("product_id") not in picked_ids
    ]
    if not candidates:
        return total, total_max, unknown_max, False

    def _completeness(covered: set[str]) -> float:
        if not required_types:
            return 1.0
        return (len(required_types) - len([t for t in required_types if t not in covered])) / len(required_types)

    victim = min(swappable, key=lambda p: p.score)
    victim_premium = victim.premium
    victim_max = victim.premium_max if victim.premium_max is not None else 0
    covered_before = {p.type for p in scored_list}
    covered_after = (covered_before - {victim.type}) | {target_type}
    # 替换后 completeness 提升（victim.type 是 required 时可能互相抵消，
    # 此时放弃置换）
    if _completeness(covered_after) <= _completeness(covered_before):
        return total, total_max, unknown_max, False

    # T 中最便宜的合格产品（满足入场/上限双校验）
    best: dict | None = None
    for cand in sorted(candidates, key=lambda c: c.get("premium", float("inf"))):
        cand_premium = cand.get("premium", 0) or 0
        cand_max = cand.get("premium_max")
        if total - victim_premium + cand_premium > max_spend:
            continue
        if cand_max is not None and total_max - victim_max + cand_max > max_spend:
            continue
        best = cand
        break
    if best is None:
        return total, total_max, unknown_max, False

    best_max = best.get("premium_max")
    picked_ids.discard(victim.product_id)
    picked_ids.add(best.get("product_id", 0))
    scored_list.remove(victim)
    scored_list.append(ScoredProduct(
        product_id=best.get("product_id", 0),
        name=best.get("name", ""),
        company=best.get("company", ""),
        type=target_type,
        premium=best.get("premium", 0) or 0,
        premium_max=best_max,
        premium_known=bool(best.get("premium_known", True)),
        deductible=best.get("deductible"),
        sum_insured=best.get("sum_insured", 0),
        source_url=best.get("source_url", ""),
        source_type=best.get("source_type", ""),
        official_verified=bool(best.get("official_verified")),
        dual_source_verified=bool(best.get("dual_source_verified")),
        third_party_review_url=best.get("third_party_review_url"),
        third_party_review_title=best.get("third_party_review_title"),
        last_verified_at=best.get("last_verified_at"),
        data_stale=bool(best.get("data_stale")),
        layer=LAYER_MAP.get(target_type, "core"),
        score=best.get("score", 0),
        score_detail=best.get("score_detail", {}),
        risk_warnings=best.get("risk_warnings", []),
        recommendation_reasons=best.get("recommendation_reasons") or [],
        not_recommended_reasons=best.get("not_recommended_reasons") or [],
    ))
    return total - victim_premium + (best.get("premium", 0) or 0), \
        total_max - victim_max + (best_max if best_max is not None else 0), \
        unknown_max or best_max is None, True


def _package_coverage_gaps(
    required_types: list[str],
    products: list[ScoredProduct],
    advice: SumInsuredAdvice,
) -> list[dict]:
    """REC-004：required 险种逐个输出保额缺口（单位元）。

    产品 sum_insured 单位为万，×10000 与建议值同口径；保额未知（null）计 0
    并在 note 标注"保额未披露"。
    """
    suggested_map = {
        "医疗险": advice.medical,
        "意外险": advice.accident,
        "重疾险": advice.critical_illness,
        "定期寿险": advice.life,
        "防癌险": advice.cancer,
    }
    gaps: list[dict] = []
    for ins_type in required_types:
        suggested = suggested_map.get(ins_type, 0)
        type_products = [p for p in products if p.type == ins_type]
        covered = 0
        undisclosed = False
        for p in type_products:
            if p.sum_insured:
                covered += p.sum_insured * 10000
            else:
                undisclosed = True
        entry: dict = {
            "type": ins_type,
            "suggested": round(suggested),
            "covered": round(covered),
            "gap": round(max(0, suggested - covered)),
        }
        if undisclosed:
            entry["note"] = "保额未披露，缺口按 0 已覆盖估算"
        gaps.append(entry)
    return gaps


def _build_single_combo(
    products_by_type: dict[str, list[dict]],
    allowed_types: set[str],
    budget: BudgetAnalysis,
    tag: str,
    label: str,
    strategy: str,
    user: UserProfile,
    sum_insured_advice: SumInsuredAdvice,
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
                # Extra bump for explicitly preferred companies.
                # 注意：这是公司偏好在评分链路中唯一实际生效的点——
                # score_product 里历史上的 pref_bonus 进 total 后被
                # apply_price_scoring 的 sum(score_detail) 覆盖，从未生效
                # （REC-005 已删除该死代码）。
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
            premium_known=bool(best.get("premium_known", True)),
            deductible=best.get("deductible"),
            sum_insured=best.get("sum_insured", 0),
            source_url=best.get("source_url", ""),
            source_type=best.get("source_type", ""),
            official_verified=bool(best.get("official_verified")),
            dual_source_verified=bool(best.get("dual_source_verified")),
            third_party_review_url=best.get("third_party_review_url"),
            third_party_review_title=best.get("third_party_review_title"),
            last_verified_at=best.get("last_verified_at"),
            data_stale=bool(best.get("data_stale")),
            layer=LAYER_MAP.get(ins_type, "core"),
            score=best.get("score", 0),
            score_detail=best.get("score_detail", {}),
            risk_warnings=best.get("risk_warnings", []),
            recommendation_reasons=best.get("recommendation_reasons") or [],
            not_recommended_reasons=best.get("not_recommended_reasons") or [],
        ))

    # required 集合只算一次；ratio/completeness/utilization 的最终口径在
    # 加补与置换之后统一重算（REC-005：删除重复的首次计算）
    required_types = _required_types_for_package(allowed_types, tag)

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
                premium_known=bool(extra.get("premium_known", True)),
                deductible=extra.get("deductible"),
                sum_insured=extra.get("sum_insured", 0),
                source_url=extra.get("source_url", ""),
                source_type=extra.get("source_type", ""),
                official_verified=bool(extra.get("official_verified")),
                dual_source_verified=bool(extra.get("dual_source_verified")),
                third_party_review_url=extra.get("third_party_review_url"),
                third_party_review_title=extra.get("third_party_review_title"),
                last_verified_at=extra.get("last_verified_at"),
                data_stale=bool(extra.get("data_stale")),
                layer="supplement",
                score=extra.get("score", 0),
                score_detail=extra.get("score_detail", {}),
                risk_warnings=extra.get("risk_warnings", []),
                recommendation_reasons=extra.get("recommendation_reasons") or [],
                not_recommended_reasons=extra.get("not_recommended_reasons") or [],
            ))

    # REC-004 一次置换 pass（star/premium 套餐，至多一轮）：存在缺失的
    # required 类型时，用该类型最便宜的合格产品替换已选中分值最低且非
    # 医疗/意外的产品；completeness 提升才采纳。budget 套餐保持"低保费优先"
    # 语义，不做置换。
    covered_types = {p.type for p in scored_list}
    missing_types = [t for t in required_types if t not in covered_types]
    if tag in ("star", "premium") and missing_types:
        total, total_max, unknown_max, _swapped = _swap_in_missing_required(
            scored_list, sorted_pools, picked_ids, required_types, missing_types,
            total, total_max, unknown_max, max_spend,
        )

    # 最终口径（加补与置换之后重算）
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
        coverage_gaps=_package_coverage_gaps(required_types, scored_list, sum_insured_advice),
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


def _scored_product_from_dict(p: dict, layer: str) -> ScoredProduct:
    """Full-field copy from a scored dict (TASK-030/034/035 fields included)."""
    return ScoredProduct(
        product_id=p.get("product_id", 0),
        name=p.get("name", ""),
        company=p.get("company", ""),
        type=p["type"],
        premium=p.get("premium", 0) or 0,
        premium_max=p.get("premium_max"),
        premium_known=bool(p.get("premium_known", True)),
        deductible=p.get("deductible"),
        sum_insured=p.get("sum_insured", 0),
        source_url=p.get("source_url", ""),
        source_type=p.get("source_type", ""),
        official_verified=bool(p.get("official_verified")),
        dual_source_verified=bool(p.get("dual_source_verified")),
        third_party_review_url=p.get("third_party_review_url"),
        third_party_review_title=p.get("third_party_review_title"),
        last_verified_at=p.get("last_verified_at"),
        data_stale=bool(p.get("data_stale")),
        layer=layer,
        score=p.get("score", 0),
        score_detail=p.get("score_detail", {}),
        risk_warnings=p.get("risk_warnings", []),
        recommendation_reasons=p.get("recommendation_reasons") or [],
        not_recommended_reasons=p.get("not_recommended_reasons") or [],
    )


def build_ai_pick_package(
    selected_ids: list[int],
    scored_products: list[dict],
    user: UserProfile,
    budget: BudgetAnalysis,
) -> ComboPackage | None:
    """Turn the AI's ranked selection into an「AI 精选」package with hard guards.

    Safety rails regardless of what the LLM returned:
    - only IDs that exist in the rule-engine scored pool are used (whitelist);
    - at most one product per insurance type (AI order wins);
    - the combined premium must respect the total budget (known upper bounds
      enforced; undisclosed maxima counted at the floor and marked "起"),
      otherwise lower-ranked picks are dropped in AI order.
    """
    by_id = {p["product_id"]: p for p in scored_products}
    max_spend = budget.total_budget
    picked: list[ScoredProduct] = []
    seen_types: set[str] = set()
    total = 0.0
    total_max = 0.0
    unknown_max = False
    for product_id in selected_ids:
        p = by_id.get(product_id)
        if p is None or p["type"] in seen_types:
            continue
        premium = p.get("premium", 0) or 0
        premium_max = p.get("premium_max")
        if total + premium > max_spend:
            continue
        if premium_max is not None and total_max + premium_max > max_spend:
            continue
        picked.append(_scored_product_from_dict(p, LAYER_MAP.get(p["type"], "core")))
        seen_types.add(p["type"])
        total += premium
        total_max += premium_max if premium_max is not None else premium
        unknown_max = unknown_max or premium_max is None
    if not picked:
        return None

    ratio = total / budget.annual_income if budget.annual_income > 0 else 0
    allowed_types = get_allowed_types(user)
    required_types = _required_types_for_package(allowed_types, "ai_pick")
    covered_types = {p.type for p in picked}
    missing_types = [t for t in required_types if t not in covered_types]
    completeness = 1.0 if not required_types else (len(required_types) - len(missing_types)) / len(required_types)
    budget_utilization = total / max(max_spend, 1)
    total_premium_max = round(total_max, 2) if total_max > 0 and not unknown_max else None
    return ComboPackage(
        tag="ai_pick",
        tag_label="✨ AI 精选方案",
        total_premium=round(total, 2),
        total_premium_max=total_premium_max,
        budget_ratio=round(ratio, 4),
        budget_utilization=round(min(budget_utilization, 1.0), 4),
        completeness_score=round(max(completeness, 0.0), 4),
        coverage_gap_notes=[f"预算或候选池限制，暂未配置{t}" for t in missing_types],
        products=picked,
    )
