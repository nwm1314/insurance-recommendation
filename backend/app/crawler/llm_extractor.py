import json
from openai import OpenAI
from backend.app.config import normalize_llm_base_url, settings

EXTRACT_PROMPT = """你是一个保险产品信息提取器。从以下网页文本中提取保险产品信息，严格按 JSON 格式输出。

{
  "name": "产品全称",
  "company": "保险公司",
  "type": "险种（重疾险/医疗险/意外险/定期寿险/防癌险/年金险）",
  "premium_min": 0,
  "premium_max": 0,
  "sum_insured_min": 0,
  "sum_insured_max": 0,
  "coverage_period": "保障期限",
  "payment_period": "缴费期限",
  "source_url": "原始页面URL",
  "disease_count": 0,
  "mild_disease_count": 0,
  "moderate_disease_count": 0,
  "has_mild_coverage": false,
  "has_moderate_coverage": false,
  "has_multi_claim": false,
  "min_age": 0,
  "max_age": 100,
  "job_class_limit": 6,
  "waiting_period_days": 90,
  "has_insured_waiver": false,
  "has_insurer_waiver": false,
  "health_disclosure_count": 0,
  "health_requirements": [],
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
- 无法提取的数值字段填 0 或默认值
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
