from sqlalchemy.orm import Session
from backend.app.models.product import Product
from backend.app.models.rule import Rule
from backend.app.engine.models import UserProfile
from backend.app.engine.budget import calculate_budget
from backend.app.engine.health import evaluate_health_match

# Age-type matching matrix: {age_group: {insurance_type: rule}}
TYPE_MATRIX = {
    "0-17":    {"医疗险": "required", "意外险": "required", "重疾险": "required", "定期寿险": "forbidden", "防癌险": "forbidden"},
    "18-25":   {"医疗险": "required", "意外险": "required", "重疾险": "required", "定期寿险": "optional", "防癌险": "forbidden"},
    "26-35":   {"医疗险": "required", "意外险": "required", "重疾险": "required", "定期寿险": "required", "防癌险": "forbidden"},
    "36-45":   {"医疗险": "required", "意外险": "required", "重疾险": "required", "定期寿险": "required", "防癌险": "forbidden"},
    "46-55":   {"医疗险": "required", "意外险": "required", "重疾险": "optional", "定期寿险": "optional", "防癌险": "required"},
    "56+":     {"医疗险": "required", "意外险": "required", "重疾险": "forbidden", "定期寿险": "forbidden", "防癌险": "required"},
}


def _get_age_group(age: int) -> str:
    if age <= 17: return "0-17"
    if age <= 25: return "18-25"
    if age <= 35: return "26-35"
    if age <= 45: return "36-45"
    if age <= 55: return "46-55"
    return "56+"


def get_allowed_types(user: UserProfile) -> set[str]:
    """Return insurance types allowed for this user"""
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


def filter_candidate_pool(db: Session, user: UserProfile) -> list[Product]:
    """Rule tree filtering: veto-based -> safe candidate pool"""
    candidates, _ = filter_candidate_pool_with_reasons(db, user)
    return candidates


def filter_candidate_pool_with_reasons(db: Session, user: UserProfile) -> tuple[list[Product], list[dict]]:
    """Rule tree filtering with explicit hard-rule and budget rejection reasons."""
    allowed_types = get_allowed_types(user)
    type_budget_limits = get_type_budget_limits(user) if user.annual_income > 0 else {}
    candidates: list[Product] = []
    rejected: list[dict] = []

    products = (
        db.query(Product)
        .join(Rule, Product.id == Rule.product_id)
        .all()
    )

    for product in products:
        rule = product.rules
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

    return candidates, rejected


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
    premium_min = product.premium_min or product.premium_max or 0
    if type_budget > 0 and premium_min > type_budget:
        return {"code": "over_budget", "reason": f"最低保费 {premium_min:.0f} 元超过该险种预算 {type_budget:.0f} 元"}

    return None
