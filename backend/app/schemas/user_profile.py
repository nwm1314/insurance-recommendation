from typing import Optional
from pydantic import BaseModel, Field


class UserProfileRequest(BaseModel):
    age: int = Field(..., ge=0, le=120, description="年龄")
    gender: str = Field(..., pattern="^(male|female)$", description="性别")
    annual_income: float = Field(..., gt=0, description="年收入（元）")
    job_class: int = Field(..., ge=1, le=6, description="职业风险等级 1-6")
    life_stage: str = Field(..., description="人生阶段")
    family_burden: str = Field(default="none", description="家庭负担")
    health_status: str = Field(default="standard", description="健康状态")
    health_issues: list[str] = Field(default_factory=list, description="健康异常项（前端编码或中文文本；后端逐项识别，未识别项会显式返回为 unknown_conditions，不静默忽略，且不构成承保判断）")
    existing_coverage: list[str] = Field(default_factory=list, description="已有保障（social=社保 / commercial=已有商业保险；规则引擎据此对可能存在重复保障的险种做软性降权与提示，不硬性排除）")
    budget_ratio: float = Field(default=0.08, ge=0.03, le=0.10, description="预算占比")
    preferred_type: Optional[str] = Field(default=None, description="指定险种偏好（医疗险/意外险/重疾险/定期寿险/防癌险/年金险；仅影响排序与 optional 险种入池，不覆盖硬规则）")
    preferred_companies: list[str] = Field(default_factory=list, description="偏好保险公司")
    enable_llm_engine: bool = Field(default=False, description="是否启用 AI 模式")
