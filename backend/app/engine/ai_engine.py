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

# AI 精排（TASK-036）：硬规则（停售/年龄/职业/健康告知/预算准入）由规则引擎先执行并
# 产出候选池；AI 在候选池白名单内做个性化选择与排序，构成「AI 精选」组合。
# 安全边界：AI 只能选白名单 ID、每险种至多 1 款、组合保费受预算上限硬校验
# （combo_builder.build_ai_pick_package 兜底截断），且不得承诺承保/医疗诊断。
STRUCTURED_SYSTEM_PROMPT = """你是保险方案精排顾问。规则引擎（硬规则 + 精算规则）已完成粗筛并给出候选池与参考套餐；你的任务是在候选池白名单内，结合用户画像做个性化的产品选择与排序，构成一份「AI 精选」组合。

严格遵循：
1. selected_product_ids 只能来自输入候选池中列出的产品 ID（白名单），不得虚构；按你认为的适配度从高到低排序。
2. 每个险种最多选择 1 款产品；组合保费合计（未披露保费上限的产品按最低价计）不得超过给定的预算上限。
3. 决策依据必须来自输入信息（画像、评分、推荐依据、健康提示），不得引入外部产品或臆造数据。
4. 不得承诺收益、保证承保、给出医疗诊断或诱导隐瞒健康告知；健康告知/既往症表述必须以"请以产品健康告知和保险公司核保为准"收尾。
5. 请严格输出 JSON 对象（无其他内容）：
{
  "selected_product_ids": [1, 2],
  "summary": "100字以内方案摘要",
  "reasoning": ["理由1", "理由2"],
  "risk_notes": ["风险提示1"],
  "comparison_notes": ["与规则套餐的对比说明1"]
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
    candidate_pool: list[dict],
    packages: list | None = None,
    budget_max_spend: float = 0.0,
) -> tuple[str, AIRecommendationExplanation] | None:
    """AI 精排：在规则引擎候选池白名单内做个性化选择与排序。

    candidate_pool 为规则引擎产出的候选产品（dict 列表，含评分/推荐依据/
    健康提示）；budget_max_spend 为组合保费硬上限（元）。返回
    (narrative, explanation)，AI 选择的组合由调用方经
    build_ai_pick_package 做预算兜底后插入套餐列表。
    Returns None if AI is unavailable or fails."""
    if not settings.llm_api_key:
        logger.warning(
            "AI rerank skipped: LLM_API_KEY is not configured (model=%s, base_url=%s)",
            settings.llm_model,
            safe_llm_base_url(settings.llm_base_url),
        )
        return None

    if not candidate_pool:
        logger.warning(
            "AI rerank skipped: no candidate products to rank (model=%s, base_url=%s)",
            settings.llm_model,
            safe_llm_base_url(settings.llm_base_url),
        )
        return None

    products_text = _build_candidates_text(candidate_pool)
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
            {
                "role": "user",
                "content": (
                    f"{user_text}\n预算上限：{budget_max_spend:.0f} 元/年（组合保费合计不得超过）\n"
                    f"规则引擎参考套餐：\n{packages_text}\n候选池（白名单，只能从中选择）：\n{products_text}"
                ),
            },
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
        allowed_ids = {int(p["product_id"]) for p in candidate_pool}
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


def _build_candidates_text(candidate_pool: list[dict]) -> str:
    """Format rule-engine candidates (with scores/reasons/warnings) for the prompt."""
    parts = []
    for p in candidate_pool:
        premium = p.get("premium", 0)
        premium_max = p.get("premium_max")
        price = f"{premium}/年" + (f"~{premium_max}" if premium_max else "起（未披露上限）")
        reasons = "；".join(p.get("recommendation_reasons") or []) or "按年龄/职业/健康/预算规则纳入候选池"
        warnings = "；".join(w.get("message", "") for w in p.get("risk_warnings") or []) or "无"
        parts.append(
            f"- ID {p['product_id']}: {p['name']}（{p['type']}）：保费 {price}，保额 {p.get('sum_insured', 0)} 万，"
            f"评分 {p.get('score', 0)}，公司 {p.get('company', '')}\n  推荐依据：{reasons}\n  健康提示：{warnings}"
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
            + "（选品时注意避免与既有保单重复保障，重复与否以保单条款为准）"
        )
    preferred = user.preferred_type or ""
    if preferred:
        lines.append(f"- 偏好险种：{preferred}（可在候选池内优先考虑该险种）")
    if user.health_issues:
        analysis = analyze_health_issues(user.health_issues)
        recognized = "、".join(
            f"{item['label']}" for item in analysis.recognized
        ) or "无"
        lines.append(f"- 健康状态：{user.health_status}，已识别异常项：{recognized}")
        if analysis.unknown_conditions:
            lines.append(
                "- 未识别健康项（候选池已按识别项过滤，未识别项不参与筛选，也不构成承保判断）："
                + "、".join(analysis.unknown_conditions)
            )
    else:
        lines.append(f"- 健康状态：{user.health_status}，异常项：无")
    return "\n".join(lines)
