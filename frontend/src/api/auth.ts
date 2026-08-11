import apiClient from './client';
import type { AuthUser, RecommendationRecord, SavedProfile } from '../types';

export function getStoredUser(): AuthUser | null {
  const raw = localStorage.getItem('auth_user');
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export async function login(email: string, password: string): Promise<AuthUser> {
  const { data } = await apiClient.post<AuthUser>('/auth/login', { email, password });
  localStorage.setItem('auth_user', JSON.stringify(data));
  window.dispatchEvent(new Event('auth-changed'));
  return data;
}

export async function register(email: string, password: string, fullName?: string): Promise<AuthUser> {
  const { data } = await apiClient.post<AuthUser>('/auth/register', {
    email,
    password,
    full_name: fullName || undefined,
  });
  localStorage.setItem('auth_user', JSON.stringify(data));
  window.dispatchEvent(new Event('auth-changed'));
  return data;
}

export async function fetchMe(): Promise<AuthUser> {
  const { data } = await apiClient.get<AuthUser>('/auth/me');
  localStorage.setItem('auth_user', JSON.stringify(data));
  window.dispatchEvent(new Event('auth-changed'));
  return data;
}

export async function logout() {
  try {
    await apiClient.post('/auth/logout');
  } finally {
    localStorage.removeItem('auth_user');
    window.dispatchEvent(new Event('auth-changed'));
  }
}

export async function fetchMyRecommendations(): Promise<RecommendationRecord[]> {
  const { data } = await apiClient.get<{ records: RecommendationRecord[] }>('/my/recommendations');
  return data.records;
}

export async function fetchMyProfiles(): Promise<SavedProfile[]> {
  const { data } = await apiClient.get<{ profiles: SavedProfile[] }>('/my/profiles');
  return data.profiles;
}

export async function fetchRecommendationDetail(id: number): Promise<RecommendationRecord> {
  const { data } = await apiClient.get<RecommendationRecord>(`/my/recommendations/${id}`);
  return data;
}

export async function fetchProfileDetail(id: number): Promise<SavedProfile> {
  const { data } = await apiClient.get<SavedProfile>(`/my/profiles/${id}`);
  return data;
}

export async function saveProfile(name: string, profile: Record<string, unknown>, note?: string): Promise<{ id: number }> {
  const { data } = await apiClient.post<{ id: number }>('/my/profiles', { name, profile, note });
  return data;
}

export async function saveRecommendation(profile: Record<string, unknown>, result: Record<string, unknown>): Promise<{ id: number }> {
  const { data } = await apiClient.post<{ id: number }>('/my/recommendations', { profile, result });
  return data;
}
export async function deleteRecommendation(id: number): Promise<void> {
  await apiClient.delete(`/my/recommendations/${id}`);
}

export async function deleteProfile(id: number): Promise<void> {
  await apiClient.delete(`/my/profiles/${id}`);
}

export async function updateProfile(id: number, name: string, profile: Record<string, unknown>, note?: string): Promise<SavedProfile> {
  const { data } = await apiClient.put<SavedProfile>(`/my/profiles/${id}`, { name, profile, note });
  return data;
}
