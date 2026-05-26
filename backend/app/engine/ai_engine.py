from typing import AsyncGenerator
from openai import AsyncOpenAI, OpenAI
from backend.app.config import settings
from backend.app.engine.models import UserProfile, ScoredProduct

SYSTEM_PROMPT = """你是一位资深保险精算师和家庭财务规划顾问。根据推荐系统为用户匹配的保险产品套餐，撰写约 200 字的个性化推荐理由。

要求：
1. 推荐语要有人情味，体现对用户家庭情况的关怀
2. 紧扣套餐中列出的具体产品进行说明（从保障全面性、性价比、投保宽松度角度），不要提及套餐外的产品
3. 若有健康异常，友好提醒核保注意事项
4. 直接输出纯文本推荐语，不要输出 JSON 格式"""


async def ai_rerank(
    user: UserProfile,
    scored_products: list[ScoredProduct],
) -> AsyncGenerator[str, None]:
    """LLM reranking with SSE streaming output of recommendation text"""
    products_text = _build_products_text(scored_products)
    user_text = _build_user_text(user)

    client = AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout=settings.llm_read_timeout,
    )

    try:
        stream = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text + "\n候选产品池：\n" + products_text},
            ],
            stream=True,
            timeout=settings.llm_read_timeout,
        )
        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                yield content
    except Exception as e:
        yield f'{{"error": "{str(e)}"}}'


async def ai_rerank_or_fallback(
    user: UserProfile,
    scored_products: list[ScoredProduct],
) -> tuple[AsyncGenerator[str, None] | None, str]:
    """Wrap AI call, return None on exception to trigger fallback"""
    try:
        gen = ai_rerank(user, scored_products)
        return gen, "ai"
    except Exception:
        return None, "degraded"


def ai_rerank_sync(
    user: UserProfile,
    package_products: list[ScoredProduct],
    packages: list | None = None,
) -> str | None:
    """Synchronous AI call — generates narrative based on the actual package products.
    Returns None if AI is unavailable or fails."""
    if not settings.llm_api_key:
        return None

    if not package_products:
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
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text + "\n推荐套餐方案：\n" + packages_text + "\n套餐包含产品：\n" + products_text},
            ],
            timeout=settings.llm_read_timeout,
        )
        return response.choices[0].message.content or ""
    except Exception:
        return None


def _build_products_text(scored_products: list[ScoredProduct]) -> str:
    return "\n".join([
        f"- {p.name}（{p.type}）：保费 {p.premium}/年，保额 {p.sum_insured} 万，评分 {p.score}，公司 {p.company}"
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
