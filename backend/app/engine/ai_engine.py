import json
import logging
from urllib.parse import urlparse
import httpx
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError
from backend.app.config import normalize_llm_base_url, safe_llm_base_url, settings
from backend.app.engine.models import UserProfile, ScoredProduct
from backend.app.engine.health import analyze_health_issues

logger = logging.getLogger(__name__)

# 说明：ai_rerank_sync 为历史命名，实际职责仅是对规则引擎已选出的套餐做解释说明，
# 不参与产品筛选与排序。选品与排序由 rule_engine（硬规则 + 精算规则）负责。
STRUCTURED_SYSTEM_PROMPT = """你是保险方案解释助手。系统已由规则引擎（硬规则 + 精算规则）完成产品筛选与套餐组合，你只能解释规则引擎已经选出的产品组合，不得新增、替换或选择套餐外的产品。

严格遵循：
1. selected_product_ids 只能来自输入中给出的套餐内产品 ID（白名单），不得虚构或越权选择。
2. 不得声称"由你完成选品/精排/AI 推荐"——选品与排序由规则引擎负责，你只负责解释。
3. 不得承诺收益、保证承保、给出医疗诊断或诱导隐瞒健康告知。
4. 涉及健康告知、既往症的表述必须以"请以产品健康告知和保险公司核保为准"收尾。
5. 请严格输出 JSON 对象（无其他内容）：
{
  "selected_product_ids": [1, 2],
  "summary": "100字以内方案摘要",
  "reasoning": ["理由1", "理由2"],
  "risk_notes": ["风险提示1"],
  "comparison_notes": ["对比说明1"]
}"""


class AIRecommendationExplanation(BaseModel):
    selected_product_ids: list[int] = Field(default_factory=list)
    summary: str = ""
    reasoning: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    comparison_notes: list[str] = Field(default_factory=list)


def _extract_json(raw_content: str) -> str | None:
    """Extract a JSON object from LLM output, tolerating markdown fences.

    Some models wrap JSON in ```json ... ``` fences or add prose around it.
    Returning None means no parseable JSON object was found.
    """
    content = raw_content.strip()
    if content.startswith("```"):
        fence = "```"
        start = content.find(fence)
        end = content.rfind(fence)
        if start != -1 and end > start:
            content = content[start + len(fence):end].strip()
            if content.lower().startswith("json"):
                content = content[len("json"):].lstrip()
    try:
        json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end <= start:
            return None
        content = content[start:end + 1]
    return content


def validate_ai_output(raw_content: str, allowed_product_ids: set[int]) -> AIRecommendationExplanation | None:
    extracted = _extract_json(raw_content)
    if extracted is None:
        return None
    try:
        data = json.loads(extracted)
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
        logger.warning(
            "AI rerank skipped: LLM_API_KEY is not configured (model=%s, base_url=%s)",
            settings.llm_model,
            safe_llm_base_url(settings.llm_base_url),
        )
        return None

    if not package_products:
        logger.warning(
            "AI rerank skipped: no package products to rerank (model=%s, base_url=%s)",
            settings.llm_model,
            safe_llm_base_url(settings.llm_base_url),
        )
        return None

    products_text = _build_products_text(package_products)
    packages_text = _build_packages_text(packages) if packages else ""
    user_text = _build_user_text(user)
    llm_base_url = normalize_llm_base_url(settings.llm_base_url)

    try:
        client = OpenAI(
            api_key=settings.llm_api_key,
            base_url=llm_base_url,
            timeout=_llm_timeout(),
            max_retries=settings.llm_max_retries,
        )
        messages = [
            {"role": "system", "content": STRUCTURED_SYSTEM_PROMPT},
            {"role": "user", "content": user_text + "\n推荐套餐方案：\n" + packages_text + "\n套餐包含产品：\n" + products_text},
        ]
        response = _create_completion(client, messages)
        content = _message_content(response)
        if not content.strip():
            logger.warning(
                "AI rerank returned empty content; retrying (model=%s, base_url=%s)",
                settings.llm_model,
                safe_llm_base_url(settings.llm_base_url),
            )
            response = _create_completion(client, messages)
            content = _message_content(response)
        allowed_ids = {product.product_id for product in package_products}
        parsed = validate_ai_output(content, allowed_ids)
        if parsed is None:
            logger.warning(
                "AI rerank failed: LLM output failed schema or product ID whitelist validation "
                "(model=%s, base_url=%s)",
                settings.llm_model,
                safe_llm_base_url(settings.llm_base_url),
            )
            return None
        narrative = render_ai_explanation(parsed)
        if not narrative:
            logger.warning(
                "AI rerank failed: LLM returned an empty narrative (model=%s, base_url=%s)",
                settings.llm_model,
                safe_llm_base_url(settings.llm_base_url),
            )
            return None
        return narrative, parsed
    except Exception as exc:
        logger.warning("AI rerank failed: %s (model=%s, base_url=%s)", exc, settings.llm_model, safe_llm_base_url(settings.llm_base_url))
        return None


def _is_deepseek_v4() -> bool:
    """Return whether the configured endpoint is DeepSeek's V4 API."""
    host = (urlparse(normalize_llm_base_url(settings.llm_base_url)).hostname or "").lower()
    return host == "api.deepseek.com" and settings.llm_model.startswith("deepseek-v4-")


def _create_completion(client, messages: list[dict]):
    """Create a bounded JSON completion with provider-specific V4 settings."""
    kwargs = {
        "model": settings.llm_model,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "max_tokens": settings.llm_max_tokens,
        "timeout": _llm_timeout(),
    }
    # DeepSeek V4 defaults to thinking mode. For this short, schema-bound
    # explanation endpoint, disabling it prevents reasoning from consuming the
    # output budget and leaving content empty/truncated.
    if _is_deepseek_v4():
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    try:
        return client.chat.completions.create(**kwargs)
    except Exception as exc:
        # Some OpenAI-compatible gateways reject response_format even though
        # they support normal chat completions. Retry once without JSON mode;
        # validate_ai_output still enforces the schema and product whitelist.
        message = str(exc).lower()
        status_code = getattr(exc, "status_code", None)
        if status_code == 400 and "response_format" in message:
            logger.warning(
                "AI rerank JSON response_format unsupported; retrying plain completion "
                "(model=%s, base_url=%s)",
                settings.llm_model,
                safe_llm_base_url(settings.llm_base_url),
            )
            kwargs.pop("response_format", None)
            return client.chat.completions.create(**kwargs)
        raise


def _llm_timeout() -> httpx.Timeout:
    """Use the short connect timeout while allowing a longer model read."""
    return httpx.Timeout(settings.llm_read_timeout, connect=settings.llm_connect_timeout)


def _message_content(response) -> str:
    """Normalize OpenAI-compatible message content into plain text."""
    content = getattr(response.choices[0].message, "content", "") or ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(getattr(part, "text", ""))
            for part in content
        )
    return str(content)


def _build_products_text(scored_products: list[ScoredProduct]) -> str:
    """Format package products with traceable rule/profile reasons for the prompt."""
    parts = []
    for p in scored_products:
        reasons = "；".join(p.recommendation_reasons) if p.recommendation_reasons else "规则引擎按年龄/职业/健康/预算规则纳入候选池"
        warnings = "；".join(w.get("message", "") for w in p.risk_warnings) if p.risk_warnings else "无"
        parts.append(
            f"- ID {p.product_id}: {p.name}（{p.type}）：保费 {p.premium}/年，保额 {p.sum_insured} 万，"
            f"评分 {p.score}，公司 {p.company}\n  推荐依据：{reasons}\n  健康提示：{warnings}"
        )
    return "\n".join(parts)


def _build_packages_text(packages: list) -> str:
    """Format package summaries for the AI prompt"""
    lines = []
    for pkg in packages:
        product_names = "、".join([p.name for p in pkg.products])
        lines.append(f"- {pkg.tag_label}：年保费 ¥{pkg.total_premium:.0f}，包含：{product_names}")
    return "\n".join(lines)


def _build_user_text(user: UserProfile) -> str:
    lines = [
        "用户画像：",
        f"- 年龄：{user.age} 岁，性别：{user.gender}",
        f"- 年收入：{user.annual_income} 元",
        f"- 人生阶段：{user.life_stage}，家庭负担：{user.family_burden}",
    ]
    if user.existing_coverage:
        lines.append(
            "- 已有保障：" + "、".join(user.existing_coverage)
            + "（规则引擎已对可能存在重复保障的险种做软性提示，不作排除）"
        )
    preferred = user.preferred_type or ""
    if preferred:
        lines.append(f"- 偏好险种：{preferred}（规则引擎据此调整类型优先级，不改变硬规则）")
    if user.health_issues:
        analysis = analyze_health_issues(user.health_issues)
        recognized = "、".join(
            f"{item['label']}" for item in analysis.recognized
        ) or "无"
        lines.append(f"- 健康状态：{user.health_status}，已识别异常项：{recognized}")
        if analysis.unknown_conditions:
            lines.append(
                "- 未识别健康项（仅作记录，不影响本次规则推荐，也不构成承保判断）："
                + "、".join(analysis.unknown_conditions)
            )
    else:
        lines.append(f"- 健康状态：{user.health_status}，异常项：无")
    return "\n".join(lines)
