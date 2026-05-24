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
    health_issues: list[str] = Field(default_factory=list, description="健康异常项")
    existing_coverage: list[str] = Field(default_factory=list, description="已有保障")
    budget_ratio: float = Field(default=0.08, ge=0.03, le=0.10, description="预算占比")
    preferred_type: Optional[str] = Field(default=None, description="指定险种偏好")
    enable_llm_engine: bool = Field(default=False, description="是否启用 AI 模式")
