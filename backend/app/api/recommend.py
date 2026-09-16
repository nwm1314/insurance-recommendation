import logging
from datetime import datetime
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.dependencies.auth import get_optional_current_user
from backend.app.models.auth import User
from backend.app.config import safe_llm_base_url, settings
from backend.app.schemas.user_profile import UserProfileRequest
from backend.app.engine.models import UserProfile, ScoredProduct
from backend.app.engine.rule_engine import filter_candidate_pool_with_profile, get_allowed_types, get_type_budget_limits
from backend.app.engine.scoring import score_product, apply_price_scoring
from backend.app.engine.budget import calculate_budget, calculate_sum_insured, calculate_coverage_gaps
from backend.app.engine.occupation import resolve_job_class
from backend.app.engine.combo_builder import build_ai_pick_package, build_combos
from backend.app.engine.ai_engine import ai_rerank_sync
from backend.app.engine.fallback import get_fallback_narrative
from backend.app.engine.health import evaluate_health_match
from backend.app.services.auth_service import save_recommendation_record
from backend.app.time import utc_now

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["recommend"])

# REC-002：价格口径说明（常量，前端 tooltip 展示）
PREMIUM_BASIS_NOTE = "价格为报价区间下限，实际以核保为准；不同产品报价条件（年龄/保额/缴费期）可能不同"


def _source_type(product) -> str:
    """official = 承保公司官网域名；aggregator = 聚合站产品详情页。"""
    url = getattr(product, "source_url", None) or ""
    if not url:
        return ""
    from backend.scripts.seed import COMPANY_URLS

    official = COMPANY_URLS.get(getattr(product, "company", "") or "")
    if official and (urlparse(url).netloc or "") == (urlparse(official).netloc or ""):
        return "official"
    return "aggregator"


def _product_freshness(product) -> tuple[str | None, bool]:
    """DATA-001：返回 (last_verified_at ISO 字符串或 None, data_stale)。

    复核时间缺失或早于 data_stale_days 天即视为过期，仅作展示标注。
    """
    verified_at = getattr(product, "last_verified_at", None)
    if verified_at is None:
        return None, True
    if isinstance(verified_at, str):
        try:
            verified_at = datetime.fromisoformat(verified_at)
        except ValueError:
            return None, True
    stale = (utc_now() - verified_at).days > settings.data_stale_days
    return verified_at.isoformat(), stale


def _run_rule_engine(db: Session, user: UserProfile) -> dict:
    """Execute the complete rule engine pipeline"""
    # Step 1: Budget + sum insured
    budget = calculate_budget(user)
    sum_insured = calculate_sum_insured(user)

    # Step 2: Rule tree filtering. Hard rules run before AI and cannot be overridden.
    candidates, rejected_products, profile_assessment = filter_candidate_pool_with_profile(db, user)

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
        last_verified_at, data_stale = _product_freshness(product)
        scored.append({
            "product_id": product.id,
            "name": product.name,
            "company": product.company,
            "type": product.type,
            "premium": product.premium_min or 0,
            # REC-002：premium_min 是否披露——未知保费拿中性价格分、不参与排名
            "premium_known": product.premium_min is not None,
            "premium_max": product.premium_max or None,
            "deductible": getattr(product, "deductible", None),
            "sum_insured": product.sum_insured_max or 0,
            "source_url": product.source_url or "",
            "source_type": _source_type(product),
            "official_verified": product.official_verification_status == "verified",
            "dual_source_verified": bool(product.dual_source_verified),
            "third_party_review_url": product.third_party_review_url or None,
            "third_party_review_title": product.third_party_review_title or None,
            "last_verified_at": last_verified_at,
            "data_stale": data_stale,
            "score": detail["total"],
            "score_detail": {k: v for k, v in detail.items() if k != "total"},
            "risk_warnings": risk_warnings,
            "recommendation_reasons": _build_recommendation_reasons(product, detail, risk_warnings),
            "not_recommended_reasons": [],
            "company_tier": getattr(product, "company_tier", 2),
        })

    # Step 4: Recalculate price scoring
    scored = apply_price_scoring(scored)

    # Step 5: Build combos（REC-004：传入保额建议以输出套餐级保额缺口）
    packages = build_combos(scored, user, budget, sum_insured)

    return {
        "budget": budget,
        "sum_insured": sum_insured,
        "packages": packages,
        "scored": scored,
        # REC-001：已有保单缺口分析（软层展示，不参与评分）
        "coverage_gaps": calculate_coverage_gaps(user, sum_insured),
        "coverage_gap_summary": _build_gap_summary(user, packages),
        "hard_rule_summary": _build_hard_rule_summary(user),
        "not_recommended_summary": _summarize_rejections(rejected_products),
        "not_recommended_details": _serialize_rejection_details(rejected_products),
        "profile_assessment": profile_assessment,
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
    # REC-003：56+ 重疾险从绝对禁止软化为 discouraged——产品可投时除外
    if user.age > 55:
        notes.append("56岁以上默认不推荐重疾险，产品可投时除外；优先考虑防癌险")
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


def _resolve_social_insurance(request: UserProfileRequest) -> str:
    """REC-001：social_insurance 未显式提供时按 existing_coverage 兼容推断。

    旧客户端不传 social_insurance、只在 existing_coverage 里写 "social"——
    这种请求按职工社保处理，行为与升级前一致。
    """
    if request.social_insurance != "none":
        return request.social_insurance
    if "social" in (request.existing_coverage or []):
        return "employee"
    return "none"


def _resolve_job_class(request: UserProfileRequest) -> int:
    """REC-001：显式 job_class 优先；否则由 occupation_name 关键词解析。

    两者都不可得时 422——职业等级影响硬过滤，不能静默猜默认值。
    """
    if request.job_class is not None:
        return request.job_class
    resolved = resolve_job_class(request.occupation_name)
    if resolved is None:
        raise HTTPException(
            status_code=422,
            detail="请选择职业风险等级（1-6 类），或提供可识别的职业名称",
        )
    return resolved


@router.post("/recommend")
def recommend(
    request: UserProfileRequest,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    user = UserProfile(
        age=request.age, gender=request.gender,
        annual_income=request.annual_income,
        job_class=_resolve_job_class(request),
        life_stage=request.life_stage, family_burden=request.family_burden,
        health_status=request.health_status, health_issues=request.health_issues,
        existing_coverage=request.existing_coverage,
        budget_ratio=request.budget_ratio,
        preferred_type=request.preferred_type,
        preferred_companies=request.preferred_companies,
        enable_llm_engine=request.enable_llm_engine,
        social_insurance=_resolve_social_insurance(request),
        occupation_name=request.occupation_name,
        existing_policies=[policy.model_dump() for policy in request.existing_policies],
    )

    result = _run_rule_engine(db, user)

    if not request.enable_llm_engine:
        response = _build_response(user, result, engine_mode="rule")
        if current_user:
            save_recommendation_record(db, current_user, request.model_dump(), response)
        return response

    # AI mode: rank candidates within the rule-engine whitelist and compose an
    # AI-pick package. Hard rules already filtered the pool; budget is enforced
    # again when materializing the AI selection.
    if not settings.llm_api_key:
        logger.warning(
            "AI mode degraded: LLM_API_KEY is not configured (model=%s, base_url=%s)",
            settings.llm_model,
            safe_llm_base_url(settings.llm_base_url),
        )
        response = _build_response(user, result, engine_mode="degraded")
        response["llm_narrative"] = "AI 模式需要配置 LLM API Key（请在 .env 中设置大写 LLM_API_KEY）。当前展示为极速规则模式推荐结果。"
        if current_user:
            save_recommendation_record(db, current_user, request.model_dump(), response)
        return response

    packages = result.get("packages", [])
    if not packages:
        logger.warning(
            "AI mode degraded: no candidate packages available (model=%s, base_url=%s)",
            settings.llm_model,
            safe_llm_base_url(settings.llm_base_url),
        )

    # Candidate pool for the AI: top-3 per insurance type by rule-engine score
    # (the pool has already cleared hard rules and per-type budget admission).
    pool_by_type: dict[str, list[dict]] = {}
    for p in sorted(result["scored"], key=lambda x: x.get("score", 0), reverse=True):
        pool_by_type.setdefault(p["type"], [])
        if len(pool_by_type[p["type"]]) < 3:
            pool_by_type[p["type"]].append(p)
    candidate_pool = [p for plist in pool_by_type.values() for p in plist]

    ai_result = ai_rerank_sync(user, candidate_pool, packages, result["budget"].total_budget)

    if ai_result:
        narrative, ai_explanation = ai_result
        ai_package = build_ai_pick_package(
            ai_explanation.selected_product_ids, result["scored"], user, result["budget"]
        )
        if ai_package is not None:
            result["packages"] = [ai_package] + list(packages)
        response = _build_response(user, result, engine_mode="ai")
        response["llm_narrative"] = narrative
        response["ai_explanation"] = ai_explanation.model_dump() if ai_explanation else None
    else:
        logger.warning(
            "AI mode degraded: LLM rerank returned no result, falling back to rule engine "
            "(model=%s, base_url=%s)",
            settings.llm_model,
            safe_llm_base_url(settings.llm_base_url),
        )
        response = _build_response(user, result, engine_mode="degraded")
        response["llm_narrative"] = get_fallback_narrative(
            result["packages"][0].products if result["packages"] else []
        )
    if current_user:
        save_recommendation_record(db, current_user, request.model_dump(), response)
    return response

def _medical_social_note(user: UserProfile) -> str | None:
    """REC-001：无社保身份的医疗险建议提示（仅文案，产品侧无社保要求字段，
    不做硬过滤）。"""
    if user.social_insurance == "none":
        return "无社保身份：商业医疗险保费通常更高，且部分产品不接受无社保人群投保，投保前请确认健康告知与社保要求"
    return None


def _build_response(user: UserProfile, result: dict, engine_mode: str = "rule") -> dict:
    budget = result["budget"]
    si = result["sum_insured"]
    packages = result["packages"]

    from backend.app.config import DEFAULT_SCORING_VERSION, ENGINE_VERSION, SCORING_WEIGHTS, scoring_weights_hash
    from backend.app.engine.rule_engine import RULE_VERSION

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
            # REC-001：无社保提示（有社保时为 null）
            "medical_social_note": _medical_social_note(user),
        },
        # REC-001：按险种的保额缺口 {"suggested", "existing", "gap"}（单位元）
        "coverage_gaps": result.get("coverage_gaps") or {},
        "packages": [
            {
                "tag": p.tag,
                "tag_label": p.tag_label,
                "total_premium": p.total_premium,
                "total_premium_max": p.total_premium_max,
                "budget_ratio": p.budget_ratio,
                "products": [
                    {
                        "id": sp.product_id, "name": sp.name, "company": sp.company,
                        "type": sp.type, "layer": sp.layer,
                        "premium": sp.premium, "premium_max": sp.premium_max, "deductible": sp.deductible, "sum_insured": sp.sum_insured,
                        # REC-002：价格口径说明 + 是否披露报价
                        "premium_basis_note": PREMIUM_BASIS_NOTE,
                        "premium_known": sp.premium_known,
                        "source_url": sp.source_url,
                        "source_type": sp.source_type,
                        "official_verified": sp.official_verified,
                        "dual_source_verified": sp.dual_source_verified,
                        "third_party_review_url": sp.third_party_review_url,
                        "third_party_review_title": sp.third_party_review_title,
                        "last_verified_at": sp.last_verified_at,
                        "data_stale": sp.data_stale,
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
                # REC-004：按 required 险种的保额缺口（单位元）
                "coverage_gaps": p.coverage_gaps,
            }
            for p in packages
        ],
        "llm_narrative": None,
        "ai_explanation": None,
        "engine_mode": engine_mode,
        # DATA-002：复现元数据——按 scoring_weights_hash 检出对应配置，
        # 按 product_id 与 created_at 查 ProductVersion 即可还原当时的
        # 引擎/规则/评分口径与产品事实。
        "meta": {
            "engine_version": ENGINE_VERSION,
            "rule_version": RULE_VERSION,
            "scoring_version": str(SCORING_WEIGHTS.get("version") or DEFAULT_SCORING_VERSION),
            "scoring_weights_hash": scoring_weights_hash(),
        },
        "hard_rule_summary": result.get("hard_rule_summary", []),
        "coverage_gap_summary": result.get("coverage_gap_summary", []),
        "not_recommended_summary": result.get("not_recommended_summary", []),
        "not_recommended_details": result.get("not_recommended_details", []),
        "profile_assessment": result.get("profile_assessment") or {
            "health": {"recognized": [], "unknown_conditions": [], "notes": []},
            "coverage": {"raw": [], "labels": {}, "marked_types": []},
            "preference": {"raw": None, "normalized": None, "valid": True},
            "assessments": [],
        },
        "disclaimer": "本方案由算法生成，仅供参考，最终承保以保险公司官方条款为准",
    }
