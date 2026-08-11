export interface UserProfile {
  age: number;
  gender: 'male' | 'female';
  annual_income: number;
  job_class: number;
  life_stage: string;
  family_burden: string;
  health_status: string;
  health_issues: string[];
  existing_coverage: string[];
  budget_ratio: number;
  preferred_type?: string;
  preferred_companies: string[];
  enable_llm_engine: boolean;
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
  };
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
