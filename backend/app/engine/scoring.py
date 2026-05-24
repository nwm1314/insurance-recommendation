from backend.app.models.product import Product
from backend.app.models.rule import Rule
from backend.app.models.benefit import Benefit
from backend.app.config import SCORING_WEIGHTS

WEIGHTS = SCORING_WEIGHTS.get("weights", {})
SCORING = SCORING_WEIGHTS.get("scoring", {})


def score_product(product: Product, rule: Rule, benefits: list[Benefit], suggested_sum_insured: float) -> dict:
    """Score a single product on 6 dimensions, return total + breakdown"""

    # Coverage completeness (25%)
    coverage = _score_coverage(product, benefits)

    # Price competitiveness (25%) - default max, recalculated in pool
    price = WEIGHTS.get("price", 0.25) * 100

    # Underwriting flexibility (20%)
    flexibility = _score_flexibility(rule)

    # Waiting period advantage (10%)
    waiting = _score_waiting(rule)

    # Waiver clauses (10%)
    waiver = _score_waiver(rule)

    # Sum insured adequacy (10%)
    adequacy = _score_adequacy(product, suggested_sum_insured)

    detail = {
        "coverage": coverage,
        "price": price,
        "flexibility": flexibility,
        "waiting": waiting,
        "adequacy": adequacy,
        "waiver": waiver,
    }
    total = sum(detail.values())
    detail["total"] = total
    return detail


def _score_coverage(product: Product, benefits: list[Benefit]) -> float:
    w = WEIGHTS.get("coverage", 0.25)
    score = 0.0
    max_score = 100.0

    # Disease count (80-180 → 0-50 points)
    if product.disease_count:
        disease_score = min(50, (product.disease_count - 80) / 100 * 50)
        score += max(0, disease_score)

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


def _score_flexibility(rule: Rule) -> float:
    w = WEIGHTS.get("flexibility", 0.20)
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


def _score_waiting(rule: Rule) -> float:
    w = WEIGHTS.get("waiting", 0.10)
    best = SCORING.get("waiting_period_best", 90)
    worst = SCORING.get("waiting_period_worst", 180)

    days = rule.waiting_period_days or 90
    if days <= best:
        return round(w * 100, 1)
    if days >= worst:
        return round(w * 50, 1)
    return round(w * (100 - 50 * (days - best) / (worst - best)), 1)


def _score_waiver(rule: Rule) -> float:
    w = WEIGHTS.get("waiver", 0.10)
    score = 0
    if rule.has_insured_waiver:
        score += 50
    if rule.has_insurer_waiver:
        score += 50
    return round((score / 100) * w * 100, 1)


def _score_adequacy(product: Product, suggested: float) -> float:
    w = WEIGHTS.get("adequacy", 0.10)
    if not suggested or not product.sum_insured_max:
        return round(w * 80, 1)
    ratio = min(product.sum_insured_max / suggested, 1.5)
    score = min(100, ratio * 100)
    return round((score / 100) * w * 100, 1)


def apply_price_scoring(scored_products: list[dict]) -> list[dict]:
    """Recalculate price competitiveness using percentile ranking within pool"""
    if not scored_products:
        return scored_products
    premiums = [p.get("premium", 0) for p in scored_products]
    min_p, max_p = min(premiums), max(premiums)
    w = WEIGHTS.get("price", 0.25)
    for p in scored_products:
        premium = p.get("premium", 0)
        if max_p > min_p:
            percentile = 1 - (premium - min_p) / (max_p - min_p)
        else:
            percentile = 1.0
        price_score = round(percentile * w * 100, 1)
        p["score_detail"]["price"] = price_score
        p["score_detail"]["total"] = sum(
            v for k, v in p["score_detail"].items() if k != "total"
        ) + price_score
        p["score"] = p["score_detail"]["total"]
    return scored_products
