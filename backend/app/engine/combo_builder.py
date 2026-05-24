from backend.app.engine.models import UserProfile, ScoredProduct, ComboPackage, BudgetAnalysis
from backend.app.engine.rule_engine import get_allowed_types


def build_combos(
    scored_products: list[dict],
    user: UserProfile,
    budget: BudgetAnalysis,
) -> list[ComboPackage]:
    """Greedy algorithm to build 3 packages"""
    allowed_types = get_allowed_types(user)
    products_by_type: dict[str, list[dict]] = {}
    for p in scored_products:
        ptype = p.get("type", "")
        if ptype not in products_by_type:
            products_by_type[ptype] = []
        products_by_type[ptype].append(p)
    for plist in products_by_type.values():
        plist.sort(key=lambda x: x.get("score", 0), reverse=True)

    combos = []

    # Package 1: Budget
    combos.append(_build_single_combo(products_by_type, allowed_types, budget, "budget", "🛡 极致性价比", user))

    # Package 2: Star
    combos.append(_build_single_combo(products_by_type, allowed_types, budget, "star", "⭐ 全面保障", user))

    # Package 3: Premium
    combos.append(_build_single_combo(products_by_type, allowed_types, budget, "premium", "👑 尊享无忧", user))

    return [c for c in combos if c.products]


def _build_single_combo(
    products_by_type: dict[str, list[dict]],
    allowed_types: set[str],
    budget: BudgetAnalysis,
    tag: str,
    label: str,
    user: UserProfile,
) -> ComboPackage:
    """Greedy selection: pick highest-scored product per type, within budget"""
    budget_mult = {"budget": 0.5, "star": 0.8, "premium": 1.0}
    max_spend = budget.total_budget * budget_mult.get(tag, 0.8)

    scored_list: list[ScoredProduct] = []
    layer_map = {
        "医疗险": "basic", "意外险": "basic",
        "重疾险": "core", "定期寿险": "core",
        "防癌险": "supplement", "年金险": "supplement",
    }

    total = 0.0
    type_order = ["医疗险", "意外险", "重疾险", "定期寿险", "防癌险"]

    for ins_type in type_order:
        if ins_type not in allowed_types:
            continue
        candidates = products_by_type.get(ins_type, [])
        if not candidates:
            continue
        best = candidates[0]
        premium = best.get("premium", 0) or 0
        if total + premium > max_spend:
            continue
        total += premium
        scored_list.append(ScoredProduct(
            product_id=best.get("product_id", 0),
            name=best.get("name", ""),
            company=best.get("company", ""),
            type=ins_type,
            premium=premium,
            sum_insured=best.get("sum_insured", 0),
            source_url=best.get("source_url", ""),
            layer=layer_map.get(ins_type, "core"),
            score=best.get("score", 0),
            score_detail=best.get("score_detail", {}),
            risk_warnings=best.get("risk_warnings", []),
        ))

    ratio = total / budget.annual_income if budget.annual_income > 0 else 0
    return ComboPackage(
        tag=tag,
        tag_label=label,
        total_premium=round(total, 2),
        budget_ratio=round(ratio, 4),
        products=scored_list,
    )
