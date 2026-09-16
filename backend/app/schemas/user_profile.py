from typing import Literal, Optional
from pydantic import BaseModel, Field


class ExistingPolicyItem(BaseModel):
    """已有保单条目（REC-001）：type 为六大险种之一，sum_insured 单位元、允许 null。"""

    type: str = Field(..., description="险种（医疗险/意外险/重疾险/定期寿险/防癌险/年金险）")
    sum_insured: Optional[float] = Field(default=None, ge=0, description="保额（元），未披露时为 null")
    annual_premium: Optional[float] = Field(default=None, ge=0, description="年保费（元）")


class UserProfileRequest(BaseModel):
    age: int = Field(..., ge=0, le=120, description="年龄")
    gender: str = Field(..., pattern="^(male|female)$", description="性别")
    annual_income: float = Field(..., gt=0, description="年收入（元）")
    job_class: Optional[int] = Field(default=None, ge=1, le=6, description="职业风险等级 1-6；未显式选择时由 occupation_name 解析")
    occupation_name: Optional[str] = Field(default=None, description="职业名称（如 程序员/矿工），仅在未显式选择 job_class 时参与解析")
    social_insurance: Literal["none", "employee", "resident", "new_rural"] = Field(
        default="none", description="社保身份：无/职工/居民/新农合"
    )
    life_stage: str = Field(..., description="人生阶段")
    family_burden: str = Field(default="none", description="家庭负担")
    health_status: str = Field(default="standard", description="健康状态")
    health_issues: list[str] = Field(default_factory=list, description="健康异常项（前端编码或中文文本；后端逐项识别，未识别项会显式返回为 unknown_conditions，不静默忽略，且不构成承保判断）")
    existing_coverage: list[str] = Field(default_factory=list, description="已有保障（social=社保 / commercial=已有商业保险；规则引擎据此对可能存在重复保障的险种做软性降权与提示，不硬性排除）")
    existing_policies: list[ExistingPolicyItem] = Field(default_factory=list, description="已有商业保单明细（险种+保额+年保费），参与重复保障软标记与保额缺口分析")
    budget_ratio: float = Field(default=0.08, ge=0.03, le=0.10, description="预算占比")
    preferred_type: Optional[str] = Field(default=None, description="指定险种偏好（医疗险/意外险/重疾险/定期寿险/防癌险/年金险；仅影响排序与 optional 险种入池，不覆盖硬规则）")
    preferred_companies: list[str] = Field(default_factory=list, description="偏好保险公司")
    enable_llm_engine: bool = Field(default=False, description="是否启用 AI 模式")
