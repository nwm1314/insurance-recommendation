import apiClient from './client';

export interface IngestionStatus {
  source_platforms: number;
  source_pages: number;
  crawl_jobs: number;
  crawl_runs: number;
  raw_documents: number;
  product_drafts: number;
  review_tasks: number;
}
export interface SourcePlatform {
  id: number;
  name: string;
  platform_type: string;
  base_url: string | null;
  robots_url: string | null;
  rate_limit_seconds: number;
  is_active: boolean;
}
export interface CrawlJob {
  id: number;
  name: string;
  source_page_id: number;
  status: string;
}
export interface SourcePage {
  id: number;
  platform_id: number;
  url: string;
  page_type: string;
  is_active: boolean;
  last_crawled_at: string | null;
}
export interface CrawlRun {
  id: number;
  crawl_job_id: number;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  http_status: number | null;
  raw_document_id: number | null;
  error_message: string | null;
}

export interface ReviewTask {
  id: number;
  product_draft_id: number;
  status: string;
  reviewer_id: number | null;
  review_note?: string | null;
  draft_name?: string | null;
  draft_type?: string | null;
  confidence?: number | null;
  created_at: string | null;
  reviewed_at?: string | null;
}

export interface ReviewTaskDetail {
  id: number;
  status: string;
  review_note: string | null;
  draft: Record<string, unknown> | null;
  confidence: number | null;
  evidence: Array<{
    field_name: string;
    field_value: string | null;
    evidence_text: string | null;
    confidence: number;
    source_url: string | null;
  }>;
  raw_document_id: number | null;
}

export async function fetchIngestionStatus(): Promise<IngestionStatus> {
  const { data } = await apiClient.get<IngestionStatus>('/admin/ingestion/status');
  return data;
}

export async function fetchSourcePlatforms(): Promise<SourcePlatform[]> {
  const { data } = await apiClient.get<{ platforms: SourcePlatform[] }>('/admin/ingestion/platforms');
  return data.platforms;
}

export async function fetchCrawlJobs(): Promise<CrawlJob[]> {
  const { data } = await apiClient.get<{ jobs: CrawlJob[] }>('/admin/ingestion/jobs');
  return data.jobs;
}

export async function fetchSourcePages(): Promise<SourcePage[]> {
  const { data } = await apiClient.get<{ pages: SourcePage[] }>('/admin/ingestion/source-pages');
  return data.pages;
}

export async function createSourcePage(payload: { platform_id: number; url: string; page_type: string }) {
  const { data } = await apiClient.post('/admin/ingestion/source-pages', payload);
  return data;
}

export async function createCrawlJob(payload: { name: string; source_page_id: number }) {
  const { data } = await apiClient.post('/admin/ingestion/jobs', payload);
  return data;
}

export async function runCrawlJob(jobId: number): Promise<{ id: number; status: string }> {
  const { data } = await apiClient.post<{ id: number; status: string }>(`/admin/ingestion/jobs/${jobId}/run`);
  return data;
}

export async function fetchCrawlRuns(): Promise<CrawlRun[]> {
  const { data } = await apiClient.get<{ runs: CrawlRun[] }>('/admin/ingestion/runs');
  return data.runs;
}

export async function fetchReviewTasks(): Promise<ReviewTask[]> {
  const { data } = await apiClient.get<{ tasks: ReviewTask[] }>('/admin/ingestion/review-tasks');
  return data.tasks;
}

export async function fetchReviewTaskDetail(taskId: number): Promise<ReviewTaskDetail> {
  const { data } = await apiClient.get<ReviewTaskDetail>(`/admin/ingestion/review-tasks/${taskId}`);
  return data;
}

export async function approveReviewTask(taskId: number, note?: string) {
  const { data } = await apiClient.post(`/admin/ingestion/review-tasks/${taskId}/approve`, { note });
  return data;
}

export async function rejectReviewTask(taskId: number, note?: string) {
  const { data } = await apiClient.post(`/admin/ingestion/review-tasks/${taskId}/reject`, { note });
  return data;
}

export async function createPlatform(payload: {
  name: string;
  platform_type?: string;
  base_url?: string;
  robots_url?: string;
  rate_limit_seconds?: number;
  is_active?: boolean;
}) {
  const { data } = await apiClient.post('/admin/ingestion/platforms', payload);
  return data;
}

export async function updatePlatform(
  platformId: number,
  payload: Partial<{
    name: string;
    platform_type: string;
    base_url: string;
    robots_url: string;
    rate_limit_seconds: number;
    is_active: boolean;
  }>
) {
  const { data } = await apiClient.put(`/admin/ingestion/platforms/${platformId}`, payload);
  return data;
}

export async function deletePlatform(platformId: number) {
  const { data } = await apiClient.delete(`/admin/ingestion/platforms/${platformId}`);
  return data;
}

export async function createManualExtraction(payload: {
  source_page_id: number;
  text: string;
  html?: string;
  extracted_data: Record<string, unknown>;
  confidence?: number;
}) {
  const { data } = await apiClient.post('/admin/ingestion/manual-extractions', payload);
  return data;
}
