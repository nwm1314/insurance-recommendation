from dataclasses import dataclass, field
from backend.app.engine.models import UserProfile
from backend.app.models.rule import Rule


# 健康异常目录：前端问卷全部选项（HomePage HEALTH_OPTIONS）逐项映射到规范条件。
# 每个规范条件给出：中文标签、关注程度（1 轻度 / 2 中度 / 3 重度，与前端分级一致，仅作提示不作承保判断）、
# 以及匹配别名（同时支持前端编码、英文编码与中文自由文本）。
# 目录外的新增健康项由 analyze_health_issues 显式返回 unknown_conditions，不静默忽略。
HEALTH_ISSUE_CATALOG: dict[str, dict] = {
    "hypertension":      {"label": "高血压", "level": 1, "aliases": ["hypertension", "高血压", "血压", "三高"]},
    "hyperlipidemia":    {"label": "高血脂/高胆固醇", "level": 1, "aliases": ["hyperlipidemia", "高血脂", "血脂", "高胆固醇", "胆固醇", "三高"]},
    "heart_disease":     {"label": "冠心病/心肌缺血", "level": 3, "aliases": ["chd", "冠心病", "心肌缺血"]},
    "arrhythmia":        {"label": "心律失常", "level": 2, "aliases": ["arrhythmia", "心律失常", "房颤", "早搏", "传导阻滞"]},
    "heart_valve":       {"label": "心脏瓣膜疾病", "level": 2, "aliases": ["valve_disease", "瓣膜", "反流", "狭窄"]},
    "congenital_heart":  {"label": "先天性心脏病", "level": 2, "aliases": ["congenital_heart", "先心"]},
    "atherosclerosis":   {"label": "动脉硬化/颈动脉斑块", "level": 2, "aliases": ["atherosclerosis", "动脉硬化", "斑块"]},
    "diabetes":          {"label": "糖尿病/血糖异常", "level": 2, "aliases": ["diabetes", "糖尿病", "血糖", "高血糖", "糖耐量", "glucose_impaired", "空腹血糖受损", "三高"]},
    "nodule":            {"label": "结节（甲状腺/乳腺/肺）", "level": 1, "aliases": ["nodule", "结节", "甲状腺结节", "乳腺结节", "肺结节"]},
    "thyroid_dysfunction": {"label": "甲状腺功能异常", "level": 1, "aliases": ["thyroid_dysfunction", "甲亢", "甲减", "桥本", "甲状腺功能"]},
    "gout":              {"label": "高尿酸血症/痛风", "level": 1, "aliases": ["gout", "痛风", "高尿酸", "尿酸"]},
    "ibd":               {"label": "炎症性肠病（IBD）", "level": 3, "aliases": ["crohns_disease", "ulcerative_colitis", "ibd", "克罗恩", "溃疡性结肠炎", "炎症性肠病"]},
    "gastritis_ulcer":   {"label": "慢性胃炎/胃溃疡", "level": 1, "aliases": ["gastritis_ulcer", "胃炎", "胃溃疡"]},
    "gerd":              {"label": "胃食管反流病", "level": 1, "aliases": ["gerd", "反流"]},
    "fatty_liver":       {"label": "脂肪肝", "level": 1, "aliases": ["fatty_liver", "脂肪肝"]},
    "hepatitis_b":       {"label": "乙肝（病毒携带/大小三阳）", "level": 2, "aliases": ["hepatitis_b", "乙肝", "小三阳", "大三阳", "肝炎"]},
    "hepatitis_other":   {"label": "丙肝/自身免疫性肝病", "level": 3, "aliases": ["hepatitis_other", "丙肝", "自免肝"]},
    "cirrhosis":         {"label": "肝硬化", "level": 3, "aliases": ["cirrhosis", "肝硬化"]},
    "gallbladder_polyp": {"label": "胆囊息肉", "level": 1, "aliases": ["gallbladder_polyp", "胆囊息肉"]},
    "pancreatitis":      {"label": "胰腺炎", "level": 2, "aliases": ["pancreatitis", "胰腺炎"]},
    "liver_cyst":        {"label": "肝囊肿/肝血管瘤", "level": 1, "aliases": ["liver_cyst", "肝囊肿", "肝血管瘤"]},
    "asthma":            {"label": "哮喘", "level": 1, "aliases": ["asthma", "哮喘"]},
    "copd":              {"label": "慢性支气管炎/慢阻肺", "level": 2, "aliases": ["copd", "慢阻肺", "慢性支气管炎"]},
    "sleep_apnea":       {"label": "睡眠呼吸暂停综合征", "level": 1, "aliases": ["sleep_apnea", "睡眠呼吸暂停"]},
    "pulmonary_history": {"label": "肺结核/肺炎史", "level": 1, "aliases": ["pulmonary_history", "肺结核", "肺炎史"]},
    "kidney_stone":      {"label": "肾结石", "level": 1, "aliases": ["kidney_stone", "肾结石"]},
    "nephritis":         {"label": "肾炎/肾功能异常", "level": 3, "aliases": ["nephritis", "肾炎", "肾功"]},
    "kidney_cyst":       {"label": "肾囊肿/多囊肾", "level": 1, "aliases": ["kidney_cyst", "肾囊肿", "多囊肾"]},
    "prostate":          {"label": "前列腺增生/前列腺炎", "level": 1, "aliases": ["prostate", "前列腺"]},
    "gyn_benign":        {"label": "子宫肌瘤/卵巢囊肿（良性）", "level": 1, "aliases": ["gyn_benign", "子宫肌瘤", "卵巢囊肿"]},
    "cin":               {"label": "宫颈上皮内瘤变（CIN）", "level": 2, "aliases": ["cin", "宫颈上皮内瘤变"]},
    "endometriosis":     {"label": "子宫内膜异位症", "level": 1, "aliases": ["endometriosis", "子宫内膜异位"]},
    "disc_herniation":   {"label": "椎间盘突出", "level": 1, "aliases": ["disc_herniation", "间盘突出"]},
    "rheumatic":         {"label": "类风湿关节炎/强直性脊柱炎", "level": 2, "aliases": ["rheumatic", "类风湿", "强直"]},
    "osteoporosis":      {"label": "骨质疏松/骨折史", "level": 1, "aliases": ["osteoporosis", "骨质疏松", "骨折史"]},
    "epilepsy":          {"label": "癫痫", "level": 2, "aliases": ["epilepsy", "癫痫"]},
    "stroke":            {"label": "脑卒中/脑梗/TIA 史", "level": 3, "aliases": ["stroke", "脑卒中", "脑梗", "tia"]},
    "neurodegenerative": {"label": "帕金森病/阿尔茨海默病", "level": 3, "aliases": ["neurodegenerative", "帕金森", "阿尔茨海默"]},
    "migraine":          {"label": "偏头痛", "level": 1, "aliases": ["migraine", "偏头痛"]},
    "benign_tumor":      {"label": "良性肿瘤（已切除）", "level": 1, "aliases": ["benign_tumor", "良性肿瘤"]},
    "cancer_remission":  {"label": "恶性肿瘤（已治愈≥5年）", "level": 3, "aliases": ["cancer_remission", "癌症", "恶性肿瘤"]},
    "cancer_active":     {"label": "恶性肿瘤（近5年/治疗中）", "level": 3, "aliases": ["cancer_active", "癌症", "恶性肿瘤", "治疗中"]},
    "tumor_marker":      {"label": "肿瘤标志物异常", "level": 2, "aliases": ["tumor_marker", "肿瘤标志物"]},
    "anemia":            {"label": "贫血", "level": 1, "aliases": ["anemia", "贫血"]},
    "blood_abnormal":    {"label": "白细胞/血小板异常", "level": 2, "aliases": ["blood_abnormal", "白细胞", "血小板"]},
    "lymphadenopathy":   {"label": "淋巴结肿大", "level": 2, "aliases": ["lymphadenopathy", "淋巴结"]},
    "hospitalization":   {"label": "住院史（近2年）", "level": 2, "aliases": ["hospitalization", "住院", "住院史", "手术"]},
    "surgery_old":       {"label": "手术史（良性/已痊愈）", "level": 1, "aliases": ["surgery_old", "手术史"]},
    "surgery_recent":    {"label": "手术史（近5年/重大）", "level": 2, "aliases": ["surgery_recent", "手术史"]},
    "organ_transplant":  {"label": "器官移植史", "level": 3, "aliases": ["organ_transplant", "器官移植"]},
    "mental_health":     {"label": "精神心理疾病", "level": 2, "aliases": ["mental_health", "抑郁", "焦虑", "双相", "精神心理"]},
    "long_term_medication": {"label": "长期服用处方药", "level": 1, "aliases": ["long_term_medication", "长期服药", "处方药"]},
    "bmi_abnormal":      {"label": "BMI 异常", "level": 1, "aliases": ["bmi_abnormal", "bmi", "肥胖"]},
    "smoking":           {"label": "吸烟史", "level": 1, "aliases": ["smoking", "吸烟"]},
    "alcohol":           {"label": "饮酒史", "level": 1, "aliases": ["alcohol", "饮酒", "酒精"]},
}

STRICT_HEALTH_TYPES = {"重疾险", "定期寿险"}

LEVEL_LABELS = {1: "轻度", 2: "中度", 3: "重度"}


@dataclass
class HealthAnalysis:
    """健康异常逐项识别结果：已识别项给出明确决策/解释，未识别项显式返回。"""
    recognized: list[dict] = field(default_factory=list)
    unknown_conditions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.recognized or self.unknown_conditions or self.notes)


def _condition_note(condition: str, entry: dict) -> str:
    label = entry["label"]
    level_label = LEVEL_LABELS.get(entry["level"], "未知")
    return (
        f"已识别「{label}」（关注程度：{level_label}）：参与健康告知规则匹配，"
        f"命中产品排除/关注清单时会在对应产品上提示；本系统不作承保判断或医疗诊断，"
        f"最终以产品健康告知与保险公司核保为准"
    )


def _match_condition(raw: str) -> str | None:
    """Return the canonical condition code matched by a raw value, or None."""
    lowered = raw.lower()
    for condition, entry in HEALTH_ISSUE_CATALOG.items():
        for alias in entry["aliases"]:
            if alias.lower() in lowered:
                return condition
    return None


def analyze_health_issues(issues: list[str] | None) -> HealthAnalysis:
    """逐项识别健康异常：返回已识别项（含决策/解释）与未知项（不静默忽略）。"""
    analysis = HealthAnalysis()
    seen: set[str] = set()
    for issue in issues or []:
        raw = str(issue).strip()
        if not raw:
            continue
        if raw in seen:
            continue
        seen.add(raw)
        condition = _match_condition(raw)
        if condition is None:
            analysis.unknown_conditions.append(raw)
            continue
        entry = HEALTH_ISSUE_CATALOG[condition]
        analysis.recognized.append({
            "code": raw,
            "condition": condition,
            "label": entry["label"],
            "level": entry["level"],
            "note": _condition_note(condition, entry),
        })
    return analysis


def normalize_health_issues(issues: list[str] | None) -> set[str]:
    """Map submitted health issues to canonical condition codes.

    Matches product health_requirements exclude/caution lists (which may use
    frontend codes, English codes or Chinese terms). Unrecognized values are
    simply not mapped here; they are surfaced separately by
    analyze_health_issues as unknown_conditions.
    """
    normalized: set[str] = set()
    for issue in issues or []:
        condition = _match_condition(str(issue))
        if condition:
            normalized.add(condition)
    return normalized


def evaluate_health_match(user: UserProfile, rule: Rule, product_type: str) -> dict | None:
    """Health-requirement matching: block (exclude) / warn (caution) per product.

    Explicitly listed health_issues are always considered — a "standard" health
    status with listed issues is treated as a disclosure inconsistency rather
    than silently ignoring the issues.
    """
    user_issues = normalize_health_issues(user.health_issues)
    if not user_issues:
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
