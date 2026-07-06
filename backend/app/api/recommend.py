import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.dependencies.auth import get_optional_current_user
from backend.app.models.auth import User
from backend.app.schemas.user_profile import UserProfileRequest
from backend.app.engine.models import UserProfile, ScoredProduct
from backend.app.engine.rule_engine import filter_candidate_pool_with_reasons, get_allowed_types, get_type_budget_limits
from backend.app.engine.scoring import score_product, apply_price_scoring
from backend.app.engine.budget import calculate_budget, calculate_sum_insured
from backend.app.engine.combo_builder import build_combos
from backend.app.engine.ai_engine import ai_rerank_sync
from backend.app.engine.fallback import get_fallback_narrative
from backend.app.engine.health import evaluate_health_match
from backend.app.services.auth_service import save_recommendation_record

router = APIRouter(prefix="/api", tags=["recommend"])


def _run_rule_engine(db: Session, user: UserProfile) -> dict:
    """Execute the complete rule engine pipeline"""
    # Step 1: Budget + sum insured
    budget = calculate_budget(user)
    sum_insured = calculate_sum_insured(user)

    # Step 2: Rule tree filtering. Hard rules run before AI and cannot be overridden.
    candidates, rejected_products = filter_candidate_pool_with_reasons(db, user)

    # Step 3: type-specific 8-dimension scoring
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
            "recommendation_reasons": _build_recommendation_reasons(product, detail, risk_warnings),
            "not_recommended_reasons": [],
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
        "coverage_gap_summary": _build_gap_summary(user, packages),
        "hard_rule_summary": _build_hard_rule_summary(user),
        "not_recommended_summary": _summarize_rejections(rejected_products),
        "not_recommended_details": _serialize_rejection_details(rejected_products),
    }


def _check_health_warnings(user: UserProfile, rule, product) -> list[dict]:
    warnings = []
    health_match = evaluate_health_match(user, rule, product.type)
    if health_match and health_match["severity"] == "warn":
        warnings.append({
            "type": health_match["code"],
            "product_name": product.name,
            "issues": health_match["issues"],
            "message": health_match["message"],
        })
    return warnings


def _build_recommendation_reasons(product, detail: dict, risk_warnings: list[dict]) -> list[str]:
    reasons = []
    strongest = sorted(
        [(k, v) for k, v in detail.items() if k != "total"],
        key=lambda item: item[1],
        reverse=True,
    )[:2]
    label_map = {
        "coverage": "保障责任相对完整",
        "price": "同险种价格竞争力较好",
        "flexibility": "投保条件相对宽松",
        "waiting": "等待期相对友好",
        "adequacy": "保额匹配度较高",
        "waiver": "豁免责任配置较好",
        "brand": "品牌稳定性较好",
        "service": "增值服务较丰富",
    }
    for key, _ in strongest:
        if key in label_map:
            reasons.append(label_map[key])
    if risk_warnings:
        reasons.append("存在健康告知关注点，需以核保结论为准")
    return reasons or [f"作为{product.type}候选产品纳入合规候选池"]


def _build_hard_rule_summary(user: UserProfile) -> list[str]:
    notes = ["已强制排除停售、年龄不符、职业等级不符的产品"]
    type_budget_limits = get_type_budget_limits(user) if user.annual_income > 0 else {}
    if type_budget_limits:
        parts = [f"{ins_type}{limit:.0f}元" for ins_type, limit in type_budget_limits.items() if limit > 0]
        if parts:
            notes.append("预算准入按险种最低保费判断：" + "、".join(parts))
    if user.age <= 17:
        notes.append("未成年人硬规则：不推荐定期寿险")
    if user.age > 55:
        notes.append("55岁以上硬规则：不推荐重疾险，优先考虑防癌险")
    return notes


def _summarize_rejections(rejected_products: list[dict]) -> list[dict]:
    summary: dict[str, dict] = {}
    for item in rejected_products:
        reason_code = item.get("reason_code") or "unknown"
        reason = item.get("reason") or "未纳入候选池"
        key = f"{reason_code}:{reason}"
        if key not in summary:
            summary[key] = {"reason_code": reason_code, "reason": reason, "count": 0, "examples": []}
        summary[key]["count"] += 1
        if len(summary[key]["examples"]) < 3:
            summary[key]["examples"].append({
                "product_id": item.get("product_id"),
                "name": item.get("name"),
                "type": item.get("type"),
            })
    return sorted(summary.values(), key=lambda item: item["count"], reverse=True)


def _serialize_rejection_details(rejected_products: list[dict], limit: int = 30) -> list[dict]:
    return [
        {
            "product_id": item.get("product_id"),
            "name": item.get("name"),
            "type": item.get("type"),
            "reason_code": item.get("reason_code") or "unknown",
            "reason": item.get("reason") or "未纳入候选池",
        }
        for item in rejected_products[:limit]
    ]


def _build_gap_summary(user: UserProfile, packages) -> list[str]:
    allowed_types = get_allowed_types(user)
    if not packages:
        return ["当前候选池不足，未形成可推荐方案"]
    best = max(packages, key=lambda pkg: pkg.completeness_score)
    notes = list(best.coverage_gap_notes)
    if "定期寿险" in allowed_types and all("定期寿险" not in {p.type for p in pkg.products} for pkg in packages):
        notes.append("家庭责任保障可能不足：未配置定期寿险")
    return notes


@router.post("/recommend")
def recommend(
    request: UserProfileRequest,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
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
        response = _build_response(user, result, engine_mode="rule")
        if current_user:
            save_recommendation_record(db, current_user, request.model_dump(), response)
        return response

    # AI mode: call LLM synchronously, return JSON with narrative
    from backend.app.config import settings
    if not settings.llm_api_key:
        response = _build_response(user, result, engine_mode="degraded")
        response["llm_narrative"] = "AI 模式需要配置 LLM API Key（请在 .env 中设置 llm_api_key）。当前展示为极速规则模式推荐结果。"
        if current_user:
            save_recommendation_record(db, current_user, request.model_dump(), response)
        return response

    # Send package products (what user actually sees) to AI, not all candidates
    packages = result.get("packages", [])
    package_products: list[ScoredProduct] = []
    if packages:
        # Use the star (middle) package as primary recommendation context
        star_pkg = packages[1] if len(packages) > 1 else packages[0]
        package_products = list(star_pkg.products)

    ai_result = ai_rerank_sync(user, package_products, packages)

    if ai_result:
        narrative, ai_explanation = ai_result
        response = _build_response(user, result, engine_mode="ai")
        response["llm_narrative"] = narrative
        response["ai_explanation"] = ai_explanation.model_dump() if ai_explanation else None
    else:
        response = _build_response(user, result, engine_mode="degraded")
        response["llm_narrative"] = get_fallback_narrative(
            result["packages"][0].products if result["packages"] else []
        )
    if current_user:
        save_recommendation_record(db, current_user, request.model_dump(), response)
    return response


async def _sse_recommend_stream(user: UserProfile, result: dict):
    """Safe SSE fallback.

    Legacy streaming rerank is intentionally disabled because it cannot enforce
    the structured AI schema and product ID whitelist used by the sync AI path.
    """
    base = _build_response(user, result, engine_mode="degraded")
    base["llm_narrative"] = get_fallback_narrative(
        result["packages"][0].products if result["packages"] else []
    )
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
            "cancer": si.cancer,
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
                        "recommendation_reasons": sp.recommendation_reasons,
                        "not_recommended_reasons": sp.not_recommended_reasons,
                    }
                    for sp in p.products
                ],
                "budget_utilization": p.budget_utilization,
                "completeness_score": p.completeness_score,
                "coverage_gap_notes": p.coverage_gap_notes,
            }
            for p in packages
        ],
        "llm_narrative": None,
        "ai_explanation": None,
        "engine_mode": engine_mode,
        "hard_rule_summary": result.get("hard_rule_summary", []),
        "coverage_gap_summary": result.get("coverage_gap_summary", []),
        "not_recommended_summary": result.get("not_recommended_summary", []),
        "not_recommended_details": result.get("not_recommended_details", []),
        "disclaimer": "本方案由算法生成，仅供参考，最终承保以保险公司官方条款为准",
    }
