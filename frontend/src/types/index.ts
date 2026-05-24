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
  enable_llm_engine: boolean;
}

export interface ScoreDetail {
  coverage: number;
  price: number;
  flexibility: number;
  waiting: number;
  adequacy: number;
  waiver: number;
}

export interface ProductItem {
  id: number;
  name: string;
  company: string;
  type: string;
  layer: string;
  premium: number;
  sum_insured: number;
  source_url: string;
  score: number;
  score_detail: ScoreDetail;
  risk_warnings: RiskWarning[];
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
  budget_ratio: number;
  products: ProductItem[];
}

export interface RecommendationResult {
  user_profile: Record<string, unknown>;
  budget_analysis: {
    annual_income: number;
    total_budget: number;
    allocation: { medical: number; accident: number; critical_illness: number; life: number };
  };
  sum_insured_advice: {
    medical: number;
    accident: number;
    critical_illness: number;
    life: number;
  };
  packages: ComboPackage[];
  llm_narrative: string | null;
  engine_mode: string;
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
