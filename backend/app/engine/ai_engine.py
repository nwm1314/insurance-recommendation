from typing import AsyncGenerator
from openai import AsyncOpenAI
from backend.app.config import settings
from backend.app.engine.models import UserProfile, ScoredProduct

SYSTEM_PROMPT = """你是一位资深保险精算师和家庭财务规划顾问。根据以下候选保险产品池和用户画像，挑选最适合用户的 3-4 款产品组合，并撰写约 200 字的个性化推荐理由。

要求：
1. 推荐语要有人情味，体现对用户家庭情况的关怀
2. 说明为什么选这几款产品（从保障全面性、性价比、投保宽松度角度）
3. 若有健康异常，友好提醒核保注意事项
4. 必须只推荐候选池中存在的产品
5. 严格按 JSON 格式输出"""


async def ai_rerank(
    user: UserProfile,
    scored_products: list[ScoredProduct],
) -> AsyncGenerator[str, None]:
    """LLM reranking with SSE streaming output of recommendation text"""
    products_text = "\n".join([
        f"- {p.name}（{p.type}）：保费 {p.premium}/年，保额 {p.sum_insured} 万，评分 {p.score}，公司 {p.company}"
        for p in scored_products
    ])
    user_text = f"""
用户画像：
- 年龄：{user.age} 岁，性别：{user.gender}
- 年收入：{user.annual_income} 元
- 人生阶段：{user.life_stage}，家庭负担：{user.family_burden}
- 健康状况：{user.health_status}，异常项：{', '.join(user.health_issues) if user.health_issues else '无'}
"""

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
            response_format={"type": "json_object"},
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
