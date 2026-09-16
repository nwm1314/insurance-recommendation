export interface UserProfile {
  age: number;
  gender: 'male' | 'female';
  annual_income: number;
  // REC-001：显式选择等级时传 1-6；改用职业名称解析时可不传（后端 422 兜底）
  job_class?: number;
  // REC-001 画像 v2：职业名称（未显式选择等级时由后端关键词解析）
  occupation_name?: string | null;
  // 社保身份：无 / 职工 / 居民 / 新农合；旧客户端不传时后端按 existing_coverage 兼容推断
  social_insurance?: 'none' | 'employee' | 'resident' | 'new_rural';
  life_stage: string;
  family_burden: string;
  health_status: string;
  health_issues: string[];
  existing_coverage: string[];
  // REC-001 已有保单明细（软层参与缺口分析与重复标记）
  existing_policies?: ExistingPolicy[];
  budget_ratio: number;
  preferred_type?: string;
  preferred_companies: string[];
  enable_llm_engine: boolean;
}

export interface ExistingPolicy {
  type: string;
  // 保额（元）；未披露时为 null
  sum_insured?: number | null;
  annual_premium?: number | null;
}

export interface ScoreDetail {
  coverage: number;
  price: number;
  flexibility: number;
  waiting: number;
  adequacy: number;
  waiver: number;
  brand: number;
  service: number;
}

export interface ProductItem {
  id: number;
  name: string;
  company: string;
  type: string;
  layer: string;
  premium: number;
  premium_max: number | null;
  deductible: number | null;
  sum_insured: number;
  source_url: string;
  // official=承保公司官网，aggregator=聚合站产品详情页；历史记录可能缺省
  source_type?: string;
  // 交叉验证标注（仅展示）：官网已验证 / 双聚合站交叉印证 / 第三方测评佐证
  official_verified?: boolean;
  dual_source_verified?: boolean;
  third_party_review_url?: string | null;
  third_party_review_title?: string | null;
  // 数据新鲜度标注（仅展示）：最近复核时间与是否超过 90 天未复核
  last_verified_at?: string | null;
  data_stale?: boolean;
  score: number;
  score_detail: ScoreDetail;
  risk_warnings: RiskWarning[];
  recommendation_reasons: string[];
  not_recommended_reasons: string[];
}

export interface RiskWarning {
  type: string;
  product_name: string;
  message: string;
}

export interface ComboPackage {
  tag: string;
  tag_label: string;
  total_premium: number;
  total_premium_max: number | null;
  budget_ratio: number;
  budget_utilization: number;
  completeness_score: number;
  coverage_gap_notes: string[];
  products: ProductItem[];
}

export interface RecognizedHealthCondition {
  code: string;
  condition: string;
  label: string;
  level: string;
  note: string;
}

export interface ProfileAssessment {
  health: {
    recognized: RecognizedHealthCondition[];
    unknown_conditions: string[];
    notes: string[];
  };
  coverage: {
    raw: string[];
    labels: Record<string, string>;
    marked_types: string[];
  };
  preference: {
    raw: string | null;
    normalized: string | null;
    valid: boolean;
  };
  assessments: Array<{
    product_id: number;
    name: string;
    type: string;
    traceable_reasons: string[];
  }>;
}

export interface RecommendationResult {
  user_profile: Record<string, unknown>;
  budget_analysis: {
    annual_income: number;
    total_budget: number;
    allocation: { medical: number; accident: number; critical_illness: number; life: number; cancer: number };
  };
  sum_insured_advice: {
    medical: number;
    accident: number;
    critical_illness: number;
    life: number;
    cancer: number;
    // REC-001：无社保身份时的医疗险建议提示（有社保/未填时为 null）
    medical_social_note?: string | null;
  };
  // REC-001：按险种的保额缺口 {"suggested","existing","gap"}（单位元）
  coverage_gaps?: Record<string, { suggested: number; existing: number; gap: number }>;
  packages: ComboPackage[];
  llm_narrative: string | null;
  ai_explanation: {
    selected_product_ids: number[];
    summary: string;
    reasoning: string[];
    risk_notes: string[];
    comparison_notes: string[];
  } | null;
  engine_mode: string;
  hard_rule_summary: string[];
  coverage_gap_summary: string[];
  not_recommended_summary: Array<{
    reason_code: string;
    reason: string;
    count: number;
    examples: Array<{ product_id: number; name: string; type: string }>;
  }>;
  not_recommended_details: Array<{
    product_id: number | null;
    name: string | null;
    type: string | null;
    reason_code: string;
    reason: string;
  }>;
  // 可选字段：TASK-029 之前保存的历史记录不含画像评估，前端须容忍缺失
  profile_assessment?: ProfileAssessment | null;
  disclaimer: string;
}

export interface ProductInfo {
  id: number;
  name: string;
  company: string;
  type: string;
  status: number;
  premium_min: number;
  premium_max: number;
  sum_insured_max: number;
}

export interface AuthUser {
  id: number;
  email: string;
  full_name: string | null;
  roles: string[];
  permissions: string[];
}

export interface AuthSession {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: AuthUser;
}

export interface RecommendationRecord {
  id: number;
  profile: Record<string, unknown>;
  result: RecommendationResult;
  created_at: string | null;
}

export interface SavedProfile {
  id: number;
  name: string;
  profile: Record<string, unknown>;
  note: string | null;
  created_at: string | null;
}
