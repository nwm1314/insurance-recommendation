"""职业名称 → 职业风险等级解析（REC-001）。

关键词包含匹配：occupations.yaml 中每类列出常见职业关键词，职业名称包含
任一关键词即视为命中该等级。同一名称命中多个等级时取最高（更保守——
等级越高可投产品越少，向高归类不会把高风险职业误配到宽松产品上）。
"""

from backend.app.config import OCCUPATIONS


def resolve_job_class(occupation_name: str | None) -> int | None:
    """Resolve a free-text occupation name to a job class 1-6.

    Returns None when the name is empty or matches no keyword — the caller
    (recommend API) turns that into a 422 instead of guessing a default.
    """
    raw = (occupation_name or "").strip()
    if not raw:
        return None
    best: int | None = None
    for class_key, keywords in (OCCUPATIONS or {}).items():
        try:
            class_value = int(str(class_key).replace("class_", ""))
        except ValueError:
            continue
        if class_value < 1 or class_value > 6:
            continue
        for keyword in keywords or []:
            if str(keyword) and str(keyword) in raw:
                if best is None or class_value > best:
                    best = class_value
                break
    return best
