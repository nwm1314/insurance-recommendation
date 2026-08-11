import apiClient from './client';
import type { UserProfile, RecommendationResult } from '../types';

export async function fetchRecommend(userProfile: UserProfile): Promise<RecommendationResult> {
  const { data } = await apiClient.post<RecommendationResult>('/recommend', userProfile);
  return data;
}