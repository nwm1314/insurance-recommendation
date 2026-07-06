import apiClient from './client';
import type { AuthSession, AuthUser, RecommendationRecord, SavedProfile } from '../types';

export function getStoredUser(): AuthUser | null {
  const raw = localStorage.getItem('auth_user');
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

function persistSession(session: AuthSession) {
  localStorage.setItem('access_token', session.access_token);
  localStorage.setItem('refresh_token', session.refresh_token);
  localStorage.setItem('auth_user', JSON.stringify(session.user));
  window.dispatchEvent(new Event('auth-changed'));
}

export async function login(email: string, password: string): Promise<AuthUser> {
  const { data } = await apiClient.post<AuthSession>('/auth/login', { email, password });
  persistSession(data);
  return data.user;
}

export async function register(email: string, password: string, fullName?: string): Promise<AuthUser> {
  const { data } = await apiClient.post<AuthSession>('/auth/register', {
    email,
    password,
    full_name: fullName || undefined,
  });
  persistSession(data);
  return data.user;
}

export async function fetchMe(): Promise<AuthUser> {
  const { data } = await apiClient.get<AuthUser>('/auth/me');
  localStorage.setItem('auth_user', JSON.stringify(data));
  window.dispatchEvent(new Event('auth-changed'));
  return data;
}

export async function logout() {
  const refreshToken = localStorage.getItem('refresh_token');
  try {
    await apiClient.post('/auth/logout', { refresh_token: refreshToken });
  } finally {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
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
