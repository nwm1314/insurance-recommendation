from sqlalchemy.orm import Session, joinedload
from backend.app.models.product import Product
from backend.app.models.rule import Rule
from backend.app.engine.models import UserProfile
from backend.app.engine.budget import calculate_budget, calculate_sum_insured
from backend.app.engine.health import analyze_health_issues, evaluate_health_match

# DATA-002：规则矩阵版本。TYPE_MATRIX 矩阵语义变更时手动递增，
# 使历史推荐结果可按响应 meta 中的 rule_version 复现。
RULE_VERSION = "2"

# Age-type matching matrix: {age_group: {insurance_type: rule}}
# REC-003 软化：
# - 56+ 重疾险 forbidden → discouraged：默认不推荐，但产品自身可投
#   （rule.max_age 覆盖用户年龄）时该产品仍可入池；
# - 46-55 防癌险 required → optional（偏好可入池，不强制）；
# - 18-45 防癌险 forbidden → optional（健康人群不再被硬拦）；
# - 0-17 定期寿险 forbidden 保持硬禁止（不可被推翻）。
TYPE_MATRIX = {
    "0-17":    {"医疗险": "required", "意外险": "required", "重疾险": "required", "定期寿险": "forbidden", "防癌险": "forbidden"},
    "18-25":   {"医疗险": "required", "意外险": "required", "重疾险": "required", "定期寿险": "optional", "防癌险": "optional"},
    "26-35":   {"医疗险": "required", "意外险": "required", "重疾险": "required", "定期寿险": "required", "防癌险": "optional"},
    "36-45":   {"医疗险": "required", "意外险": "required", "重疾险": "required", "定期寿险": "required", "防癌险": "optional"},
    "46-55":   {"医疗险": "required", "意外险": "required", "重疾险": "optional", "定期寿险": "optional", "防癌险": "optional"},
    "56+":     {"医疗险": "required", "意外险": "required", "重疾险": "discouraged", "定期寿险": "forbidden", "防癌险": "optional"},
}

PREFERRED_TYPE_LABELS = {
    "医疗险": "医疗险",
    "意外险": "意外险",
    "重疾险": "重疾险",
    "定期寿险": "定期寿险",
    "防癌险": "防癌险",
    "年金险": "年金险",
}

EXISTING_COVERAGE_LABELS = {
    "social": "社保",
    "commercial": "已有商业保险",
}


def normalize_preferred_type(value) -> str | None:
    """Validate a preferred-type value; return canonical type or None if invalid/absent."""
    if value is None:
        return None
    v = str(value).strip() if not isinstance(value, str) else value.strip()
    return v if v in PREFERRED_TYPE_LABELS else None


def _get_age_group(age: int) -> str:
    if age <= 17: return "0-17"
    if age <= 25: return "18-25"
    if age <= 35: return "26-35"
    if age <= 45: return "36-45"
    if age <= 55: return "46-55"
    return "56+"


def get_allowed_types(user: UserProfile) -> set[str]:
    """Return insurance types allowed for this user.

    Hard rules (forbidden types) always win. A preferred_type may promote an
    age-optional type into the plan (soft preference, never overrides
    forbidden); preferred types that are already required/optional-in-budget
    keep their existing semantics.
    """
    allowed, _discouraged = get_allowed_and_discouraged_types(user)
    return allowed


def get_allowed_and_discouraged_types(user: UserProfile) -> tuple[set[str], set[str]]:
    """REC-003：返回 (allowed, discouraged)。

    - forbidden：硬禁止，永不入池；
    - discouraged：默认不入池（不在 allowed 中），但保留为独立集合——
      逐产品判定时若产品自身可投（rule.max_age 覆盖用户年龄），该产品
      仍可入池（仅此产品，不整类放开）；
    - optional：按绝对预算分层入池；
    - required：始终入池。
    """
    budget_tier = _get_budget_tier(user)
    age_group = _get_age_group(user.age)
    allowed: set[str] = set()
    discouraged: set[str] = set()
    for ins_type, rule in TYPE_MATRIX.get(age_group, {}).items():
        if rule == "forbidden":
            continue
        if rule == "required":
            allowed.add(ins_type)  # always include required types
        elif rule == "optional" and ins_type in budget_tier:
            allowed.add(ins_type)
        elif rule == "discouraged":
            discouraged.add(ins_type)
    preferred = normalize_preferred_type(user.preferred_type)
    if preferred and preferred in TYPE_MATRIX.get(age_group, {}):
        if TYPE_MATRIX[age_group][preferred] in ("optional", "discouraged"):
            # 偏好可把 optional/discouraged 类型提回池（discouraged 的产品级
            # 复原之外再给一个显式偏好通道，仍不越过 forbidden）
            allowed.add(preferred)
            discouraged.discard(preferred)
    return allowed, discouraged


# REC-003：绝对年预算分层（budget_rules.yaml absolute_budget_tiers 缺失时
# 回退内置值——模式与 scoring.py 的 yaml 校验回退一致）。分层只看总预算：
# 用户 slider 通过 total_budget = income × ratio 间接影响分层，不再直接
# 按 ratio 决定险种集合（30 万收入 × 3% = 9000 元预算应可配重疾）。
_ABSOLUTE_BUDGET_TIERS_FALLBACK = [
    {"max_budget": 1000, "types": ["医疗险", "意外险"]},
    {"max_budget": 3000, "types": ["医疗险", "意外险", "重疾险"]},
    {"max_budget": 6000, "types": ["医疗险", "意外险", "重疾险", "定期寿险"]},
    {"max_budget": None, "types": ["医疗险", "意外险", "重疾险", "定期寿险", "防癌险"]},
]


def _get_budget_tier(user: UserProfile) -> set[str]:
    """按绝对年预算（total_budget）决定 optional 险种集合。"""
    from backend.app.config import BUDGET_RULES

    budget = calculate_budget(user)
    tiers = BUDGET_RULES.get("absolute_budget_tiers") or _ABSOLUTE_BUDGET_TIERS_FALLBACK
    for tier in tiers:
        max_budget = tier.get("max_budget")
        if max_budget is None or budget.total_budget <= max_budget:
            return set(tier.get("types") or [])
    # 兜底：最后一个 none 上限层未配置时返回最保守集合
    return {"医疗险", "意外险"}


TYPE_BUDGET_KEYS = {
    "医疗险": "medical",
    "意外险": "accident",
    "重疾险": "critical_illness",
    "定期寿险": "life",
    "防癌险": "cancer",
}


def get_type_budget_limits(user: UserProfile) -> dict[str, float]:
    budget = calculate_budget(user)
    return {
        ins_type: budget.total_budget * budget.allocation.get(key, 0)
        for ins_type, key in TYPE_BUDGET_KEYS.items()
    }


def _existing_policy_amount_for(user: UserProfile, product_type: str) -> float:
    """Sum disclosed sum-insured of the user's existing policies of one type (元)."""
    total = 0.0
    for policy in user.existing_policies or []:
        if isinstance(policy, dict) and (policy.get("type") or "").strip() == product_type:
            total += policy.get("sum_insured") or 0
    return total


def evaluate_coverage_duplicate(user: UserProfile, product_type: str) -> dict | None:
    """Soft duplicate-coverage mark for a product type based on existing_coverage.

    Never hard-excludes: marks are informational and feed ranking tie-breaks.
    REC-001: existing_policies 精确到险种+保额——同险种已披露保额合计达到建议
    保额的 50% 以上时，升级为"已有同类较高保额"提示（比泛化的 commercial
    标记更具体）。
    """
    existing_total = _existing_policy_amount_for(user, product_type)
    if existing_total > 0:
        advice = calculate_sum_insured(user)
        suggested = {
            "医疗险": advice.medical,
            "意外险": advice.accident,
            "重疾险": advice.critical_illness,
            "定期寿险": advice.life,
            "防癌险": advice.cancer,
        }.get(product_type)
        if suggested and existing_total >= suggested * 0.5:
            return {
                "code": "high_existing_coverage",
                "label": "已有同类较高保额",
                "note": f"您已持有同类保障约{existing_total:.0f}元保额（建议保额{suggested:.0f}元的 50% 以上），再次配置边际作用有限，请按实际需求决定；系统不排除推荐，仅作提示",
            }
    coverage = set(user.existing_coverage or [])
    if "commercial" in coverage:
        return {
            "code": "duplicate_coverage",
            "label": "重复保障",
            "note": "已填写「已有商业保险」：同类保障可能存在重复配置，建议核对既有保单；系统不排除推荐，仅作提示，不构成承保判断",
        }
    if "social" in coverage and product_type == "医疗险":
        return {
            "code": "partial_duplicate",
            "label": "部分重复保障",
            "note": "社保仅覆盖医保目录内费用，商业医疗险主要用于补充目录外与自费部分，是否重复以具体保单条款为准；系统仅作提示",
        }
    return None


def preferred_type_priority(user: UserProfile, product_type: str) -> float:
    """Ranking weight: 1.0 when the product type matches the user's preferred type."""
    if normalize_preferred_type(user.preferred_type) == product_type:
        return 1.0
    return 0.0


def premium_range_info(product: Product) -> dict:
    """Explicit quote-range semantics for a product (TASK-016).

    - ``premium_min``: lower bound of the product quote range (None when the
      product carries no quote info at all).
    - ``premium_max``: upper bound of the product quote range (None when the
      product has no upper bound — the actual price is only confirmable by
      underwriting, so display must fall back to the lower bound and mark
      "以核保为准").
    - ``max_unknown``: True when the upper bound is missing.
    """
    return {
        "premium_min": product.premium_min,
        "premium_max": product.premium_max,
        "max_unknown": product.premium_max is None,
    }


def budget_fit_for_range(product: Product, user: UserProfile) -> str:
    """Classify how a candidate product's quote range relates to its type budget.

    - ``fit``: upper bound known and within the type budget (or no type budget
      configured, e.g. zero income) — the full range is affordable.
    - ``max_may_exceed``: upper bound known but above the type budget — only the
      lower end of the range is affordable; combo assembly must not let the
      plan's max total blow the budget.
    - ``unknown_max``: no upper bound — the range is open-ended; display shows
      the lower bound and defers the price to underwriting ("以核保为准").
    """
    info = premium_range_info(product)
    if info["max_unknown"]:
        return "unknown_max"
    type_budget_limits = get_type_budget_limits(user) if user.annual_income > 0 else {}
    type_budget = type_budget_limits.get(product.type, 0)
    if type_budget > 0 and info["premium_max"] > type_budget:
        return "max_may_exceed"
    return "fit"


def filter_candidate_pool(db: Session, user: UserProfile) -> list[Product]:
    """Rule tree filtering: veto-based -> safe candidate pool"""
    candidates, _ = filter_candidate_pool_with_reasons(db, user)
    return candidates


def filter_candidate_pool_with_reasons(db: Session, user: UserProfile) -> tuple[list[Product], list[dict]]:
    """Rule tree filtering with explicit hard-rule and budget rejection reasons.

    Candidate order is profile-aware (tie-break only): preferred-type products
    first, duplicate-coverage products last. Products are never excluded for
    existing coverage or type preference — hard rules alone decide exclusion.
    REC-003：discouraged 类型（如 56+ 重疾）默认不入池，但逐产品判定时，
    产品自身 rule.max_age 覆盖用户年龄 → 该产品入池（仅此产品）。
    """
    allowed_types, discouraged_types = get_allowed_and_discouraged_types(user)
    type_budget_limits = get_type_budget_limits(user) if user.annual_income > 0 else {}
    candidates: list[Product] = []
    rejected: list[dict] = []

    # OPS-005：joinedload 一次取回 rules/benefits，消除逐产品的 N+1 查询
    products = db.query(Product).options(
        joinedload(Product.rules), joinedload(Product.benefits)
    ).all()

    for product in products:
        rule = product.rules
        if product.status != 1:
            rejected.append({
                "product_id": product.id,
                "name": product.name,
                "type": product.type,
                "reason_code": "inactive",
                "reason": "产品已停售或暂不可售",
            })
            continue
        if rule is None:
            rejected.append({
                "product_id": product.id,
                "name": product.name,
                "type": product.type,
                "reason_code": "missing_rule",
                "reason": "产品缺少投保规则，不可作为可售产品推荐",
            })
            continue
        rejection = _product_rejection_reason(product, rule, user, allowed_types, type_budget_limits, discouraged_types)
        if rejection:
            rejected.append({
                "product_id": product.id,
                "name": product.name,
                "type": product.type,
                "reason_code": rejection["code"],
                "reason": rejection["reason"],
            })
            continue
        candidates.append(product)

    preferred = normalize_preferred_type(user.preferred_type)

    def _profile_order_key(product: Product) -> tuple[int, int]:
        pref_rank = 0 if (preferred and product.type == preferred) else 1
        dup_rank = 1 if evaluate_coverage_duplicate(user, product.type) else 0
        return (pref_rank, dup_rank)

    candidates.sort(key=_profile_order_key)

    return candidates, rejected


def assess_product_profile(user: UserProfile, product: Product, rule: Rule, allowed_types: set[str] | None = None) -> dict:
    """Per-product traceable profile assessment: which rule / which profile field
    drove the decision, including soft coverage marks and health matching.

    OPS-005：allowed_types 由调用方传入（同请求内计算一次），避免逐产品
    重复计算。
    """
    health_match = evaluate_health_match(user, rule, product.type)
    coverage = evaluate_coverage_duplicate(user, product.type)
    preferred = normalize_preferred_type(user.preferred_type)
    reasons: list[str] = []

    if preferred and product.type == preferred:
        reasons.append(f"命中险种偏好：{preferred}")
    if coverage:
        reasons.append(f"{coverage['label']}：{coverage['note']}")
    if health_match:
        reasons.append(health_match["message"])

    return {
        "product_id": product.id,
        "name": product.name,
        "type": product.type,
        "premium_range": premium_range_info(product),
        "budget_fit": budget_fit_for_range(product, user),
        "coverage_duplicate": coverage,
        "preferred_type": {
            "value": preferred,
            "matches": bool(preferred and product.type == preferred),
        },
        "health_match": health_match,
        "rules": {
            "age_group": _get_age_group(user.age),
            "age_allowed": rule.min_age <= user.age <= rule.max_age,
            "job_class_allowed": user.job_class <= rule.job_class_limit,
            "type_allowed": product.type in (allowed_types if allowed_types is not None else get_allowed_types(user)),
        },
        "traceable_reasons": reasons,
    }


def filter_candidate_pool_with_profile(
    db: Session, user: UserProfile
) -> tuple[list[Product], list[dict], dict]:
    """Candidate pool filtering plus profile-level analysis.

    Returns (candidates, rejected, profile_assessment) where profile_assessment
    includes per-candidate traceable assessments, health analysis (recognized /
    unknown conditions), coverage marks and preference validity.
    """
    candidates, rejected = filter_candidate_pool_with_reasons(db, user)
    # OPS-005：allowed_types 只计算一次并传给逐产品评估
    allowed_types, _discouraged = get_allowed_and_discouraged_types(user)
    assessments = []
    for product in candidates:
        assessments.append(assess_product_profile(user, product, product.rules, allowed_types))

    health_analysis = analyze_health_issues(user.health_issues)
    coverage = set(user.existing_coverage or [])
    preferred = normalize_preferred_type(user.preferred_type)

    return candidates, rejected, {
        "health": {
            "recognized": health_analysis.recognized,
            "unknown_conditions": health_analysis.unknown_conditions,
            "notes": health_analysis.notes,
        },
        "coverage": {
            "raw": sorted(coverage),
            "labels": {c: EXISTING_COVERAGE_LABELS.get(c, c) for c in coverage},
            "marked_types": sorted({
                p["type"] for p in assessments if p["coverage_duplicate"]
            }),
        },
        "preference": {
            "raw": user.preferred_type,
            "normalized": preferred,
            "valid": preferred is not None or not user.preferred_type,
        },
        "assessments": assessments,
    }


def _product_rejection_reason(
    product: Product,
    rule: Rule,
    user: UserProfile,
    allowed_types: set[str],
    type_budget_limits: dict[str, float],
    discouraged_types: set[str] | None = None,
) -> dict | None:
    if product.status != 1:
        return {"code": "inactive", "reason": "产品已停售或暂不可售"}
    if product.type not in allowed_types:
        # REC-003：discouraged 类型（默认不推荐）的产品级复原——产品自身
        # 可投年龄覆盖用户年龄时放行该产品，不整类放开。
        if discouraged_types and product.type in discouraged_types:
            if rule.max_age >= user.age:
                pass  # 逐项继续走年龄/职业/健康与预算校验
            else:
                return {
                    "code": "type_not_in_plan",
                    "reason": "该险种对此年龄默认不推荐，且产品投保年龄不覆盖当前年龄",
                }
        else:
            if product.type == "定期寿险" and user.age <= 17:
                return {"code": "type_forbidden", "reason": "未成年人硬规则不推荐定期寿险"}
            return {"code": "type_not_in_plan", "reason": "当前年龄或预算层级下不配置该险种"}
    if rule.min_age > user.age or rule.max_age < user.age:
        return {"code": "age_not_allowed", "reason": f"投保年龄不匹配，允许 {rule.min_age}-{rule.max_age} 岁"}
    if rule.job_class_limit < user.job_class:
        return {"code": "job_class_not_allowed", "reason": f"职业等级超过产品限制，产品最高支持 {rule.job_class_limit} 类"}

    health_match = evaluate_health_match(user, rule, product.type)
    if health_match and health_match["severity"] == "block":
        return {"code": health_match["code"], "reason": health_match["message"]}

    type_budget = type_budget_limits.get(product.type, 0)
    range_info = premium_range_info(product)
    premium_min = range_info["premium_min"] or range_info["premium_max"] or 0
    if type_budget > 0 and premium_min > type_budget:
        return {"code": "over_budget", "reason": f"最低保费 {premium_min:.0f} 元超过该险种预算 {type_budget:.0f} 元"}

    return None
