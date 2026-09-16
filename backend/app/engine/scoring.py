from backend.app.models.product import Product
from backend.app.models.rule import Rule
from backend.app.models.benefit import Benefit
from backend.app.config import SCORING_WEIGHTS, settings
import logging

WEIGHTS = SCORING_WEIGHTS.get("weights", {})
SCORING = SCORING_WEIGHTS.get("scoring", {})
SCORE_DIMENSIONS = ["coverage", "price", "flexibility", "waiting", "adequacy", "waiver", "brand", "service"]

DEFAULT_TYPE_WEIGHTS = {
    "医疗险": {"coverage": 0.24, "price": 0.16, "flexibility": 0.18, "waiting": 0.08, "adequacy": 0.14, "waiver": 0.04, "brand": 0.08, "service": 0.08},
    "重疾险": {"coverage": 0.24, "price": 0.18, "flexibility": 0.14, "waiting": 0.08, "adequacy": 0.14, "waiver": 0.10, "brand": 0.08, "service": 0.04},
    "意外险": {"coverage": 0.20, "price": 0.22, "flexibility": 0.16, "waiting": 0.04, "adequacy": 0.20, "waiver": 0.02, "brand": 0.08, "service": 0.08},
    "定期寿险": {"coverage": 0.16, "price": 0.24, "flexibility": 0.18, "waiting": 0.08, "adequacy": 0.18, "waiver": 0.04, "brand": 0.08, "service": 0.04},
    "防癌险": {"coverage": 0.22, "price": 0.16, "flexibility": 0.20, "waiting": 0.08, "adequacy": 0.16, "waiver": 0.04, "brand": 0.08, "service": 0.06},
}


def _type_weights(product_type: str) -> dict[str, float]:
    if validate_type_weights():
        weights = DEFAULT_TYPE_WEIGHTS.get(product_type) or WEIGHTS
        return _normalize_type_weights(product_type, weights)
    configured = SCORING_WEIGHTS.get("type_weights", {})
    weights = configured.get(product_type) or DEFAULT_TYPE_WEIGHTS.get(product_type) or WEIGHTS
    return _normalize_type_weights(product_type, weights)


def _normalize_type_weights(product_type: str, weights: dict[str, float]) -> dict[str, float]:
    merged = {dimension: float(weights.get(dimension, WEIGHTS.get(dimension, 0))) for dimension in SCORE_DIMENSIONS}
    total = sum(merged.values())
    if total <= 0:
        fallback = DEFAULT_TYPE_WEIGHTS.get(product_type) or {dimension: WEIGHTS.get(dimension, 0) for dimension in SCORE_DIMENSIONS}
        total = sum(fallback.values()) or 1
        return {dimension: fallback.get(dimension, 0) / total for dimension in SCORE_DIMENSIONS}
    if abs(total - 1.0) > 0.0001:
        return {dimension: round(value / total, 6) for dimension, value in merged.items()}
    return merged


def validate_type_weights() -> list[str]:
    errors = []
    base_weights = SCORING_WEIGHTS.get("weights", {})
    if not base_weights:
        errors.append("weights 配置缺失")
    else:
        missing_base = [dimension for dimension in SCORE_DIMENSIONS if dimension not in base_weights]
        if missing_base:
            errors.append(f"weights 缺少权重字段: {', '.join(missing_base)}")
        base_total = sum(float(base_weights.get(dimension, 0)) for dimension in SCORE_DIMENSIONS)
        if abs(base_total - 1.0) > 0.0001:
            errors.append(f"weights 权重合计为 {base_total:.4f}，应为 1.0000")

    configured = SCORING_WEIGHTS.get("type_weights", {})
    if not configured:
        errors.append("type_weights 配置缺失")
        return errors

    missing_types = [product_type for product_type in DEFAULT_TYPE_WEIGHTS if product_type not in configured]
    if missing_types:
        errors.append(f"type_weights 缺少险种: {', '.join(missing_types)}")

    for product_type, weights in configured.items():
        missing = [dimension for dimension in SCORE_DIMENSIONS if dimension not in weights]
        if missing:
            errors.append(f"{product_type} 缺少权重字段: {', '.join(missing)}")
        total = sum(float(weights.get(dimension, 0)) for dimension in SCORE_DIMENSIONS)
        if abs(total - 1.0) > 0.0001:
            errors.append(f"{product_type} 权重合计为 {total:.4f}，应为 1.0000")
    return errors


def validate_scoring_weights_on_startup(logger: logging.Logger | None = None) -> list[str]:
    logger = logger or logging.getLogger(__name__)
    errors = validate_type_weights()
    if errors:
        logger.warning(
            "scoring_weights.yaml 配置异常，将使用内置默认险种权重: %s",
            "; ".join(errors),
        )
        if settings.scoring_weights_fail_fast:
            raise RuntimeError("scoring_weights.yaml 配置异常: " + "; ".join(errors))
    else:
        logger.info("scoring_weights.yaml 配置校验通过")
    return errors


def _weight(weights: dict[str, float], key: str, fallback: float) -> float:
    return weights.get(key, WEIGHTS.get(key, fallback))


def score_product(
    product: Product, rule: Rule, benefits: list[Benefit],
    suggested_sum_insured: float,
    preferred_companies: list[str] | None = None,
) -> dict:
    """Score a single product with insurance-type-specific 8-dimension weights.

    preferred_companies 参数保留以兼容调用方，但当前不参与评分——历史上
    的 pref_bonus 进 total 后会被 apply_price_scoring 的 sum(score_detail)
    覆盖，从未生效（REC-005 已删除）；公司偏好的唯一实际生效点是
    combo_builder.tier_adjusted_score 的 +0.12 偏好加成。
    """
    weights = _type_weights(product.type)

    coverage = _score_coverage(product, benefits, weights)

    # Price competitiveness is recalculated within each insurance type pool.
    price = _weight(weights, "price", 0.18) * 100

    flexibility = _score_flexibility(rule, weights)

    waiting = _score_waiting(rule, weights, product.type)

    waiver = _score_waiver(rule, weights)

    adequacy = _score_adequacy(product, suggested_sum_insured, weights)

    brand = _score_brand(product, weights)

    service = _score_service(product, benefits, weights)

    detail = {
        "coverage": coverage,
        "price": price,
        "flexibility": flexibility,
        "waiting": waiting,
        "adequacy": adequacy,
        "waiver": waiver,
        "brand": brand,
        "service": service,
    }
    detail["total"] = sum(detail.values())
    return detail


def _score_coverage(product: Product, benefits: list[Benefit], weights: dict[str, float]) -> float:
    w = _weight(weights, "coverage", 0.25)
    score = 0.0
    max_score = 100.0

    # REC-003 险种特化：disease_count（重病种数）只对重疾/防癌有意义，
    # 医疗/意外/寿险不再使用该分量，其 50 分量并入 benefit_count 与
    # 类型自有布尔（避免医疗险因无病种数被压到 50 分上限以下）。
    counts_diseases = product.type in ("重疾险", "防癌险")
    if counts_diseases:
        # Disease count (80-180 → 0-50 points)
        if product.disease_count:
            disease_score = min(50, (product.disease_count - 80) / 100 * 50)
            score += max(0, disease_score)
    else:
        # 非重疾/防癌：基础责任数量（basic benefits 含轻微/中症等条目）
        # 顶替病种数分量（0-50，每条 10 分封顶 50）
        benefit_count = len([b for b in benefits if b.benefit_type == "basic"])
        score += min(50, benefit_count * 10)

    # Has mild +10, has moderate +10
    if product.has_mild_coverage:
        score += 10
    if product.has_moderate_coverage:
        score += 10

    # Multi-claim +15
    if product.has_multi_claim:
        score += 15

    # Benefit count (more = better, capped at 15)
    benefit_count = len([b for b in benefits if b.benefit_type == "basic"])
    score += min(15, benefit_count * 1.5)

    return round((score / max_score) * w * 100, 1)


def _score_flexibility(rule: Rule, weights: dict[str, float]) -> float:
    w = _weight(weights, "flexibility", 0.20)
    best = SCORING.get("health_disclosure_best", 3)
    worst = SCORING.get("health_disclosure_worst", 15)
    job_best = SCORING.get("job_class_best", 6)

    # Health disclosure leniency (fewer = better, 0-50)
    health_count = rule.health_disclosure_count or 0
    if health_count <= best:
        health_score = 50
    elif health_count >= worst:
        health_score = 0
    else:
        health_score = 50 * (1 - (health_count - best) / (worst - best))

    # Job class leniency (higher = better, 0-50)
    job_score = 50 * (rule.job_class_limit / job_best)

    return round(((health_score + job_score) / 100) * w * 100, 1)


def _score_waiting(rule: Rule, weights: dict[str, float], product_type: str | None = None) -> float:
    w = _weight(weights, "waiting", 0.10)
    # REC-003：waiting_period_best 支持按险种覆盖——意外险（通常无等待期）
    # 与医疗险的最优等待期与长期险不同。yaml 缺失时回退全局 best。
    best_by_type = SCORING.get("waiting_period_best_by_type") or {}
    if product_type and product_type in best_by_type:
        best = best_by_type[product_type]
    else:
        best = SCORING.get("waiting_period_best", 90)
    worst = SCORING.get("waiting_period_worst", 180)

    # 注意用 is not None 判断：意外险等待期 0 天是合法值，`or 90` 会把 0
    # 静默替换成 90（REC-003 按险种 best=0 评分时必须保留 0）
    days = rule.waiting_period_days if rule.waiting_period_days is not None else 90
    if days <= best:
        return round(w * 100, 1)
    if days >= worst:
        return round(w * 50, 1)
    return round(w * (100 - 50 * (days - best) / (worst - best)), 1)


def _score_waiver(rule: Rule, weights: dict[str, float]) -> float:
    w = _weight(weights, "waiver", 0.10)
    score = 0
    if rule.has_insured_waiver:
        score += 50
    if rule.has_insurer_waiver:
        score += 50
    return round((score / 100) * w * 100, 1)


def _score_adequacy(product: Product, suggested: float, weights: dict[str, float]) -> float:
    w = _weight(weights, "adequacy", 0.10)
    if not suggested or not product.sum_insured_max:
        return round(w * 80, 1)
    # sum_insured_max is stored in 万, suggested is in 元
    si_max_yuan = product.sum_insured_max * 10000
    ratio = min(si_max_yuan / suggested, 1.5)
    score = min(100, ratio * 100)
    return round((score / 100) * w * 100, 1)


def _score_brand(product: Product, weights: dict[str, float]) -> float:
    """Brand trust based on company tier"""
    w = _weight(weights, "brand", 0.10)
    tier_map = SCORING_WEIGHTS.get("company_tier_brand", {1: 85, 2: 75, 3: 65})
    tier = getattr(product, "company_tier", 2)
    brand_score = tier_map.get(tier, 75)
    return round((brand_score / 100) * w * 100, 1)


def _score_service(product: Product, benefits: list[Benefit], weights: dict[str, float]) -> float:
    """Value-added services: green channel, second opinion, drug delivery, etc."""
    w = _weight(weights, "service", 0.07)
    special_count = len([b for b in benefits if b.benefit_type in ("special", "waiver")])
    tier = getattr(product, "company_tier", 2)
    tier_bonus = {1: 35, 2: 50, 3: 25}.get(tier, 35)
    score = min(100, tier_bonus + special_count * 15)
    return round((score / 100) * w * 100, 1)


def apply_price_scoring(scored_products: list[dict]) -> list[dict]:
    """Recalculate price competitiveness within each insurance type.

    REC-002：排名百分位 + 未知中性。
    - 仅对 premium_known=True（premium_min 已披露）的产品计算价格分：按保费
      升序排名，percentile = 1 - rank/(n-1)，最便宜得满权重、最贵得 0。
      旧的 min-max 归一会给中间价位产品接近满分的虚高价格分（如
      [100, 200, 100000] 中的 200），排名百分位消除了这种失真；
    - premium_known=False 的产品价格分 = 0.5 × w × 100（中性），不参与
      排名——保费未知不等于有竞争力，也不等于没竞争力；
    - n==1 时该池内唯一已知产品给满权重（无比较基准，维持旧口径）。
    """
    if not scored_products:
        return scored_products

    by_type: dict[str, list[dict]] = {}
    for product in scored_products:
        by_type.setdefault(product.get("type", ""), []).append(product)

    for products in by_type.values():
        product_type = products[0].get("type", "")
        w = _weight(_type_weights(product_type), "price", 0.18)

        known = [p for p in products if p.get("premium_known")]
        unknown = [p for p in products if not p.get("premium_known")]
        neutral_price = round(0.5 * w * 100, 1)

        # 保费升序排名（premium_min or 0：未知产品不参与）
        ranked = sorted(known, key=lambda p: p.get("premium", 0))
        n = len(ranked)
        for rank, p in enumerate(ranked):
            if n == 1:
                percentile = 1.0
            else:
                percentile = 1 - rank / (n - 1)
            p["score_detail"]["price"] = round(percentile * w * 100, 1)

        for p in unknown:
            p["score_detail"]["price"] = neutral_price

        for p in products:
            p["score"] = sum(p["score_detail"].values())
    return scored_products
