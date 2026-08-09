import json
import logging
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError
from backend.app.config import settings
from backend.app.engine.models import UserProfile, ScoredProduct

logger = logging.getLogger(__name__)

STRUCTURED_SYSTEM_PROMPT = """你是一位保险推荐解释助手。你只能解释系统已经选出的产品，不得新增、替换或选择候选池外产品。

请严格输出 JSON 对象：
{
  "selected_product_ids": [1, 2],
  "summary": "100字以内方案摘要",
  "reasoning": ["理由1", "理由2"],
  "risk_notes": ["风险提示1"],
  "comparison_notes": ["对比说明1"]
}

要求：
1. selected_product_ids 只能来自输入产品 ID。
2. 不得承诺收益、保证承保或诱导隐瞒健康告知。
3. 不得输出 JSON 以外的内容。"""


class AIRecommendationExplanation(BaseModel):
    selected_product_ids: list[int] = Field(default_factory=list)
    summary: str = ""
    reasoning: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    comparison_notes: list[str] = Field(default_factory=list)


def validate_ai_output(raw_content: str, allowed_product_ids: set[int]) -> AIRecommendationExplanation | None:
    try:
        data = json.loads(raw_content)
        parsed = AIRecommendationExplanation.model_validate(data)
    except (json.JSONDecodeError, ValidationError, TypeError):
        return None

    if any(product_id not in allowed_product_ids for product_id in parsed.selected_product_ids):
        return None
    return parsed


def render_ai_explanation(explanation: AIRecommendationExplanation) -> str:
    parts = []
    if explanation.summary:
        parts.append(explanation.summary)
    if explanation.reasoning:
        parts.append("推荐理由：" + "；".join(explanation.reasoning))
    if explanation.comparison_notes:
        parts.append("对比说明：" + "；".join(explanation.comparison_notes))
    if explanation.risk_notes:
        parts.append("注意事项：" + "；".join(explanation.risk_notes))
    return "\n".join(parts).strip()


def ai_rerank_sync(
    user: UserProfile,
    package_products: list[ScoredProduct],
    packages: list | None = None,
) -> tuple[str, AIRecommendationExplanation | None] | None:
    """Synchronous AI call that returns validated structured explanation.
    Returns None if AI is unavailable or fails."""
    if not settings.llm_api_key:
        logger.warning("AI rerank skipped: llm_api_key is not configured")
        return None

    if not package_products:
        logger.warning("AI rerank skipped: no package products to rerank")
        return None

    products_text = _build_products_text(package_products)
    packages_text = _build_packages_text(packages) if packages else ""
    user_text = _build_user_text(user)

    client = OpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout=settings.llm_read_timeout,
    )

    try:
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": STRUCTURED_SYSTEM_PROMPT},
                {"role": "user", "content": user_text + "\n推荐套餐方案：\n" + packages_text + "\n套餐包含产品：\n" + products_text},
            ],
            response_format={"type": "json_object"},
            timeout=settings.llm_read_timeout,
        )
        content = response.choices[0].message.content or ""
        allowed_ids = {product.product_id for product in package_products}
        parsed = validate_ai_output(content, allowed_ids)
        if parsed is None:
            logger.warning("AI rerank failed: LLM output failed schema or product ID whitelist validation")
            return None
        narrative = render_ai_explanation(parsed)
        return narrative, parsed
    except Exception as exc:
        logger.warning("AI rerank failed: %s (model=%s, base_url=%s)", exc, settings.llm_model, settings.llm_base_url)
        return None


def _build_products_text(scored_products: list[ScoredProduct]) -> str:
    return "\n".join([
        f"- ID {p.product_id}: {p.name}（{p.type}）：保费 {p.premium}/年，保额 {p.sum_insured} 万，评分 {p.score}，公司 {p.company}"
        for p in scored_products
    ])


def _build_packages_text(packages: list) -> str:
    """Format package summaries for the AI prompt"""
    lines = []
    for pkg in packages:
        product_names = "、".join([p.name for p in pkg.products])
        lines.append(f"- {pkg.tag_label}：年保费 ¥{pkg.total_premium:.0f}，包含：{product_names}")
    return "\n".join(lines)


def _build_user_text(user: UserProfile) -> str:
    return f"""
用户画像：
- 年龄：{user.age} 岁，性别：{user.gender}
- 年收入：{user.annual_income} 元
- 人生阶段：{user.life_stage}，家庭负担：{user.family_burden}
- 健康状况：{user.health_status}，异常项：{', '.join(user.health_issues) if user.health_issues else '无'}
"""
