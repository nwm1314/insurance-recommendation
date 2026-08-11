from sqlalchemy.orm import Session
from backend.app.models.product import Product
from backend.app.models.rule import Rule
from backend.app.engine.models import UserProfile
from backend.app.engine.budget import calculate_budget
from backend.app.engine.health import analyze_health_issues, evaluate_health_match

# Age-type matching matrix: {age_group: {insurance_type: rule}}
TYPE_MATRIX = {
    "0-17":    {"医疗险": "required", "意外险": "required", "重疾险": "required", "定期寿险": "forbidden", "防癌险": "forbidden"},
    "18-25":   {"医疗险": "required", "意外险": "required", "重疾险": "required", "定期寿险": "optional", "防癌险": "forbidden"},
    "26-35":   {"医疗险": "required", "意外险": "required", "重疾险": "required", "定期寿险": "required", "防癌险": "forbidden"},
    "36-45":   {"医疗险": "required", "意外险": "required", "重疾险": "required", "定期寿险": "required", "防癌险": "forbidden"},
    "46-55":   {"医疗险": "required", "意外险": "required", "重疾险": "optional", "定期寿险": "optional", "防癌险": "required"},
    "56+":     {"医疗险": "required", "意外险": "required", "重疾险": "forbidden", "定期寿险": "forbidden", "防癌险": "required"},
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
    budget_tier = _get_budget_tier(user.budget_ratio)
    age_group = _get_age_group(user.age)
    allowed = set()
    for ins_type, rule in TYPE_MATRIX.get(age_group, {}).items():
        if rule == "forbidden":
            continue
        if rule == "required":
            allowed.add(ins_type)  # always include required types
        elif rule == "optional" and ins_type in budget_tier:
            allowed.add(ins_type)
    preferred = normalize_preferred_type(user.preferred_type)
    if preferred and preferred in TYPE_MATRIX.get(age_group, {}):
        if TYPE_MATRIX[age_group][preferred] == "optional":
            allowed.add(preferred)
    return allowed


def _get_budget_tier(ratio: float) -> set[str]:
    if ratio <= 0.03:
        return {"医疗险", "意外险"}
    if ratio <= 0.05:
        return {"医疗险", "意外险", "重疾险"}
    if ratio <= 0.08:
        return {"医疗险", "意外险", "重疾险", "定期寿险"}
    return {"医疗险", "意外险", "重疾险", "定期寿险", "防癌险"}


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


def evaluate_coverage_duplicate(user: UserProfile, product_type: str) -> dict | None:
    """Soft duplicate-coverage mark for a product type based on existing_coverage.

    Never hard-excludes: marks are informational and feed ranking tie-breaks.
    """
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
    """
    allowed_types = get_allowed_types(user)
    type_budget_limits = get_type_budget_limits(user) if user.annual_income > 0 else {}
    candidates: list[Product] = []
    rejected: list[dict] = []

    products = db.query(Product).all()

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
        rejection = _product_rejection_reason(product, rule, user, allowed_types, type_budget_limits)
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


def assess_product_profile(user: UserProfile, product: Product, rule: Rule) -> dict:
    """Per-product traceable profile assessment: which rule / which profile field
    drove the decision, including soft coverage marks and health matching."""
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
            "type_allowed": product.type in get_allowed_types(user),
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
    assessments = []
    for product in candidates:
        assessments.append(assess_product_profile(user, product, product.rules))

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
) -> dict | None:
    if product.status != 1:
        return {"code": "inactive", "reason": "产品已停售或暂不可售"}
    if product.type not in allowed_types:
        if product.type == "定期寿险" and user.age <= 17:
            return {"code": "type_forbidden", "reason": "未成年人硬规则不推荐定期寿险"}
        if product.type == "重疾险" and user.age > 55:
            return {"code": "type_forbidden", "reason": "55岁以上硬规则不推荐重疾险"}
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
