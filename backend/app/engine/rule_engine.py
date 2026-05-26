from sqlalchemy.orm import Session
from backend.app.models.product import Product
from backend.app.models.rule import Rule
from backend.app.engine.models import UserProfile

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


def filter_candidate_pool(db: Session, user: UserProfile) -> list[Product]:
    """Rule tree filtering: veto-based -> safe candidate pool"""
    allowed_types = get_allowed_types(user)

    query = (
        db.query(Product)
        .join(Rule, Product.id == Rule.product_id)
        .filter(Product.status == 1)
        .filter(Product.type.in_(allowed_types))
        .filter(Rule.min_age <= user.age)
        .filter(Rule.max_age >= user.age)
        .filter(Rule.job_class_limit >= user.job_class)
    )

    if user.annual_income > 0:
        max_premium = user.annual_income * user.budget_ratio
        if max_premium > 0:
            query = query.filter(Product.premium_max <= max_premium)

    return query.all()
