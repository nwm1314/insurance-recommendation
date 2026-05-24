from backend.app.engine.models import ScoredProduct


FALLBACK_MESSAGE = "AI 线路繁忙，已自动切换至极速专家推荐"


def get_fallback_narrative(products: list[ScoredProduct]) -> str:
    """Generate rule-based recommendation text on degradation"""
    if not products:
        return "暂未找到完全匹配的产品方案，请调整筛选条件后重试。"
    names = "、".join([p.name for p in products[:3]])
    return f"{FALLBACK_MESSAGE}。为您推荐：{names}，该方案基于您的画像通过精算规则筛选，确保合规与性价比。"
