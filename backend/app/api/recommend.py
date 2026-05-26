import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.schemas.user_profile import UserProfileRequest
from backend.app.engine.models import UserProfile, ScoredProduct
from backend.app.engine.rule_engine import filter_candidate_pool
from backend.app.engine.scoring import score_product, apply_price_scoring
from backend.app.engine.budget import calculate_budget, calculate_sum_insured
from backend.app.engine.combo_builder import build_combos
from backend.app.engine.ai_engine import ai_rerank_or_fallback
from backend.app.engine.fallback import get_fallback_narrative

router = APIRouter(prefix="/api", tags=["recommend"])


def _run_rule_engine(db: Session, user: UserProfile) -> dict:
    """Execute the complete rule engine pipeline"""
    # Step 1: Rule tree filtering
    candidates = filter_candidate_pool(db, user)

    # Step 2: Budget + sum insured
    budget = calculate_budget(user)
    sum_insured = calculate_sum_insured(user)

    # Step 3: 6-dimension scoring
    scored = []
    si_map = {
        "医疗险": sum_insured.medical,
        "意外险": sum_insured.accident,
        "重疾险": sum_insured.critical_illness,
        "定期寿险": sum_insured.life,
        "防癌险": sum_insured.cancer,
    }

    for product in candidates:
        rule = product.rules
        benefits = product.benefits
        suggested_si = si_map.get(product.type, 500000)
        detail = score_product(product, rule, benefits, suggested_si, user.preferred_companies)
        risk_warnings = _check_health_warnings(user, rule, product)
        scored.append({
            "product_id": product.id,
            "name": product.name,
            "company": product.company,
            "type": product.type,
            "premium": product.premium_min or 0,
            "sum_insured": product.sum_insured_max or 0,
            "source_url": product.source_url or "",
            "score": detail["total"],
            "score_detail": {k: v for k, v in detail.items() if k != "total"},
            "risk_warnings": risk_warnings,
            "company_tier": getattr(product, "company_tier", 2),
        })

    # Step 4: Recalculate price scoring
    scored = apply_price_scoring(scored)

    # Step 5: Build combos
    packages = build_combos(scored, user, budget)

    return {
        "budget": budget,
        "sum_insured": sum_insured,
        "packages": packages,
        "scored": scored,
    }


def _check_health_warnings(user: UserProfile, rule, product) -> list[dict]:
    warnings = []
    if user.health_status != "standard" and user.health_issues:
        warnings.append({
            "type": "health",
            "product_name": product.name,
            "message": "您的健康异常项可能涉及该产品健康告知，建议走智能核保",
        })
    return warnings


@router.post("/recommend")
def recommend(request: UserProfileRequest, db: Session = Depends(get_db)):
    user = UserProfile(
        age=request.age, gender=request.gender,
        annual_income=request.annual_income, job_class=request.job_class,
        life_stage=request.life_stage, family_burden=request.family_burden,
        health_status=request.health_status, health_issues=request.health_issues,
        existing_coverage=request.existing_coverage,
        budget_ratio=request.budget_ratio,
        preferred_type=request.preferred_type,
        preferred_companies=request.preferred_companies,
        enable_llm_engine=request.enable_llm_engine,
    )

    result = _run_rule_engine(db, user)

    if not request.enable_llm_engine:
        return _build_response(user, result, engine_mode="rule")

    # AI mode: call LLM synchronously, return JSON with narrative
    from backend.app.config import settings
    if not settings.llm_api_key:
        response = _build_response(user, result, engine_mode="degraded")
        response["llm_narrative"] = "AI 模式需要配置 LLM API Key（请在 .env 中设置 llm_api_key）。当前展示为极速规则模式推荐结果。"
        return response

    # Send package products (what user actually sees) to AI, not all candidates
    packages = result.get("packages", [])
    package_products: list[ScoredProduct] = []
    if packages:
        # Use the star (middle) package as primary recommendation context
        star_pkg = packages[1] if len(packages) > 1 else packages[0]
        package_products = list(star_pkg.products)

    from backend.app.engine.ai_engine import ai_rerank_sync
    narrative = ai_rerank_sync(user, package_products, packages)

    if narrative:
        response = _build_response(user, result, engine_mode="ai")
        response["llm_narrative"] = narrative
    else:
        response = _build_response(user, result, engine_mode="degraded")
        response["llm_narrative"] = get_fallback_narrative(
            result["packages"][0].products if result["packages"] else []
        )
    return response


async def _sse_recommend_stream(user: UserProfile, result: dict):
    """SSE streaming AI recommendation"""
    # Send rule engine result first
    base = _build_response(user, result, engine_mode="ai")
    base["llm_narrative"] = ""
    yield f"data: {json.dumps(base, ensure_ascii=False)}\n\n"

    scored_dicts = result.get("scored", [])
    scored_products = [
        ScoredProduct(
            product_id=p.get("product_id", 0),
            name=p.get("name", ""),
            company=p.get("company", ""),
            type=p.get("type", ""),
            premium=p.get("premium", 0),
            sum_insured=p.get("sum_insured", 0),
            source_url=p.get("source_url", ""),
            layer=p.get("layer", "core"),
            score=p.get("score", 0),
            score_detail=p.get("score_detail", {}),
            risk_warnings=p.get("risk_warnings", []),
        )
        for p in scored_dicts
    ]
    ai_gen, mode = await ai_rerank_or_fallback(user, scored_products)

    if mode == "degraded" or ai_gen is None:
        base["llm_narrative"] = get_fallback_narrative(
            result["packages"][0].products if result["packages"] else []
        )
        base["engine_mode"] = "degraded"
        yield f"data: {json.dumps(base, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
        return

    narrative_parts = []
    async for chunk in ai_gen:
        narrative_parts.append(chunk)
        base["llm_narrative"] = "".join(narrative_parts)
        yield f"data: {json.dumps(base, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


def _build_response(user: UserProfile, result: dict, engine_mode: str = "rule") -> dict:
    budget = result["budget"]
    si = result["sum_insured"]
    packages = result["packages"]

    return {
        "user_profile": {
            "age": user.age, "gender": user.gender,
            "annual_income": user.annual_income,
            "life_stage": user.life_stage, "health_status": user.health_status,
        },
        "budget_analysis": {
            "annual_income": budget.annual_income,
            "total_budget": budget.total_budget,
            "allocation": budget.allocation,
        },
        "sum_insured_advice": {
            "medical": si.medical,
            "accident": si.accident,
            "critical_illness": si.critical_illness,
            "life": si.life,
        },
        "packages": [
            {
                "tag": p.tag,
                "tag_label": p.tag_label,
                "total_premium": p.total_premium,
                "budget_ratio": p.budget_ratio,
                "products": [
                    {
                        "id": sp.product_id, "name": sp.name, "company": sp.company,
                        "type": sp.type, "layer": sp.layer,
                        "premium": sp.premium, "sum_insured": sp.sum_insured,
                        "source_url": sp.source_url,
                        "score": sp.score, "score_detail": sp.score_detail,
                        "risk_warnings": sp.risk_warnings,
                    }
                    for sp in p.products
                ],
            }
            for p in packages
        ],
        "llm_narrative": None,
        "engine_mode": engine_mode,
        "disclaimer": "本方案由算法生成，仅供参考，最终承保以保险公司官方条款为准",
    }
