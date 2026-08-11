import apiClient from './client';
import type { ProductInfo } from '../types';

export interface ProductListResponse {
  total: number;
  page: number;
  page_size: number;
  products: ProductInfo[];
}

export async function fetchProducts(type?: string, page = 1, pageSize = 20, search?: string): Promise<ProductListResponse> {
  const { data } = await apiClient.get<ProductListResponse>('/products', {
    params: { type, page, page_size: pageSize, search },
  });
  return data;
}

export async function fetchProductDetail(id: number): Promise<unknown> {
  const { data } = await apiClient.get(`/products/${id}`);
  return data;
}

export interface ProductCreateRequest {
  name: string;
  company: string;
  type: string;
  status?: number;
  premium_min?: number;
  premium_max?: number;
  sum_insured_min?: number;
  sum_insured_max?: number;
  coverage_period?: string;
  payment_period?: string;
  source_url?: string;
  deductible?: number;
  disease_count?: number;
  mild_disease_count?: number;
  moderate_disease_count?: number;
  has_mild_coverage?: boolean;
  has_moderate_coverage?: boolean;
  has_multi_claim?: boolean;
  company_tier?: number;
  rule?: {
    min_age?: number;
    max_age?: number;
    job_class_limit?: number;
    waiting_period_days?: number;
    has_insured_waiver?: boolean;
    has_insurer_waiver?: boolean;
    health_disclosure_count?: number;
    health_requirements?: string[];
  };
  benefits?: Array<{
    benefit_type?: string;
    benefit_name: string;
    benefit_amount?: string;
    payment_limit?: string;
    desc?: string;
  }>;
}

export interface ProductResponse {
  id: number;
  name: string;
  company: string;
  type: string;
  status: number;
  premium_min: number;
  premium_max: number;
  sum_insured_min: number;
  sum_insured_max: number;
  coverage_period: string;
  payment_period: string;
  deductible: number;
  disease_count: number;
  mild_disease_count: number;
  moderate_disease_count: number;
  has_mild_coverage: boolean;
  has_moderate_coverage: boolean;
  has_multi_claim: boolean;
  company_tier: number;
  source_url: string;
}

export async function createProduct(payload: ProductCreateRequest): Promise<ProductResponse> {
  const { data } = await apiClient.post<ProductResponse>('/products', payload);
  return data;
}

export async function updateProduct(id: number, payload: Partial<ProductCreateRequest>): Promise<ProductResponse> {
  const { data } = await apiClient.put<ProductResponse>(`/products/${id}`, payload);
  return data;
}

export async function deleteProduct(id: number): Promise<void> {
  await apiClient.delete(`/products/${id}`);
}
