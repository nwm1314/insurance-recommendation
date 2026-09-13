import json
from openai import OpenAI
from backend.app.config import normalize_llm_base_url, settings

EXTRACT_PROMPT = """你是一个保险产品信息提取器。从以下网页文本中提取保险产品信息，严格按 JSON 格式输出。

{
  "name": "产品全称",
  "company": "保险公司",
  "type": "险种（重疾险/医疗险/意外险/定期寿险/防癌险/年金险）",
  "premium_min": null,
  "premium_max": null,
  "sum_insured_min": null,
  "sum_insured_max": null,
  "coverage_period": "保障期限",
  "payment_period": "缴费期限",
  "source_url": "原始页面URL",
  "deductible": null,
  "disease_count": null,
  "mild_disease_count": 0,
  "moderate_disease_count": 0,
  "has_mild_coverage": false,
  "has_moderate_coverage": false,
  "has_multi_claim": false,
  "min_age": null,
  "max_age": null,
  "job_class_limit": null,
  "waiting_period_days": null,
  "has_insured_waiver": null,
  "has_insurer_waiver": null,
  "health_disclosure_count": null,
  "health_requirements": {"exclude": [], "caution": []},
  "benefits": [
    {
      "benefit_type": "basic",
      "benefit_name": "责任名称",
      "benefit_amount": "赔付金额描述",
      "payment_limit": "赔付上限"
    }
  ]
}

规则：
- 无法从页面确认的字段一律输出 null（禁止填 0、禁止猜测默认值）；保费/保额数字必须是页面原文数字，不得推算
- 允许输出 null 的字段：min_age, max_age, job_class_limit, waiting_period_days, has_insured_waiver, has_insurer_waiver, health_disclosure_count, health_requirements, premium_min, premium_max, sum_insured_min, sum_insured_max, deductible, disease_count
- health_requirements 必须是结构化对象：{"exclude": [...], "caution": [...]}。exclude=产品条款明确不可投保的健康异常；caution=需健康告知/核保关注的异常；元素用条款原文中的中文名词；页面未提及健康要求时输出 {"exclude": [], "caution": []}；无法判断时输出 null
- type 必须严格匹配枚举值
- benefits 数组从网页保障责任段落提取
- 所有金额单位为"元"
"""


def extract_product(text: str) -> dict | None:
    """Extract structured product info using LLM"""
    client = OpenAI(
        api_key=settings.llm_api_key,
        base_url=normalize_llm_base_url(settings.llm_base_url),
        timeout=settings.llm_read_timeout,
    )

    for attempt in range(settings.llm_max_retries):
        try:
            response = client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {"role": "system", "content": EXTRACT_PROMPT},
                    # 24k 字符兼顾覆盖产品页保费/责任段落与 LLM token 成本
                    {"role": "user", "content": text[:24000]},
                ],
                response_format={"type": "json_object"},
                timeout=settings.llm_read_timeout,
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except Exception as e:
            if attempt == settings.llm_max_retries - 1:
                print(f"LLM extraction failed after {settings.llm_max_retries} retries: {e}")
                return None
    return None
