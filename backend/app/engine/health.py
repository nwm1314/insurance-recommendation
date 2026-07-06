from backend.app.engine.models import UserProfile
from backend.app.models.rule import Rule


HEALTH_ISSUE_ALIASES = {
    "nodule": ["nodule", "结节", "甲状腺结节", "乳腺结节", "肺结节"],
    "hypertension": ["hypertension", "高血压", "三高", "血压"],
    "hyperlipidemia": ["hyperlipidemia", "高血脂", "三高", "血脂"],
    "diabetes": ["diabetes", "糖尿病", "高血糖", "三高", "血糖"],
    "hepatitis_b": ["hepatitis_b", "乙肝", "小三阳", "大三阳", "肝炎"],
    "hospitalization": ["hospitalization", "住院", "手术", "住院史", "手术史"],
}

STRICT_HEALTH_TYPES = {"重疾险", "定期寿险"}


def normalize_health_issues(issues: list[str]) -> set[str]:
    normalized: set[str] = set()
    for issue in issues or []:
        raw = str(issue).strip().lower()
        for code, aliases in HEALTH_ISSUE_ALIASES.items():
            if raw == code or any(alias.lower() in raw for alias in aliases):
                normalized.add(code)
    return normalized


def evaluate_health_match(user: UserProfile, rule: Rule, product_type: str) -> dict | None:
    user_issues = normalize_health_issues(user.health_issues)
    if user.health_status == "standard" or not user_issues:
        return None

    requirements = _normalize_requirements(rule.health_requirements)
    blocked = user_issues & requirements.get("exclude", set())
    caution = user_issues & requirements.get("caution", set())

    if blocked:
        return {
            "severity": "block",
            "code": "health_issue_mismatch",
            "issues": sorted(blocked),
            "message": f"健康异常 {', '.join(sorted(blocked))} 命中产品明确排除项",
        }
    if caution:
        return {
            "severity": "warn",
            "code": "health_notice_risk",
            "issues": sorted(caution),
            "message": f"健康异常 {', '.join(sorted(caution))} 可能触发健康告知，请以核保结论为准",
        }
    if product_type in STRICT_HEALTH_TYPES:
        return {
            "severity": "warn",
            "code": "health_notice_risk",
            "issues": sorted(user_issues),
            "message": "重疾险/寿险对健康告知更严格，建议重点核对既往症和检查异常",
        }
    return None


def _normalize_requirements(raw) -> dict[str, set[str]]:
    if not raw:
        return {"exclude": set(), "caution": set()}
    if isinstance(raw, dict):
        return {
            "exclude": normalize_health_issues(raw.get("exclude", [])),
            "caution": normalize_health_issues(raw.get("caution", [])),
        }
    if isinstance(raw, list):
        return {"exclude": set(), "caution": normalize_health_issues([str(item) for item in raw])}
    return {"exclude": set(), "caution": normalize_health_issues([str(raw)])}
