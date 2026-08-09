import axios, { InternalAxiosRequestConfig } from 'axios';
import { message } from 'antd';

const apiClient = axios.create({
  baseURL: '/api',
  timeout: 120000,
  headers: { 'Content-Type': 'application/json' },
});

function clearSession() {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('auth_user');
  window.dispatchEvent(new Event('auth-changed'));
}

interface RetryableConfig {
  _retried?: boolean;
}

let refreshPromise: Promise<boolean> | null = null;

async function tryRefreshToken(): Promise<boolean> {
  const refreshToken = localStorage.getItem('refresh_token');
  if (!refreshToken) return false;
  if (!refreshPromise) {
    refreshPromise = axios
      .post('/api/auth/refresh', { refresh_token: refreshToken })
      .then(({ data }) => {
        localStorage.setItem('access_token', data.access_token);
        localStorage.setItem('refresh_token', data.refresh_token);
        localStorage.setItem('auth_user', JSON.stringify(data.user));
        window.dispatchEvent(new Event('auth-changed'));
        return true;
      })
      .catch(() => false)
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config as (InternalAxiosRequestConfig & RetryableConfig) | undefined;
    if (err.response?.status === 401 && original && !original._retried) {
      const refreshed = await tryRefreshToken();
      if (refreshed) {
        original._retried = true;
        original.headers.Authorization = `Bearer ${localStorage.getItem('access_token')}`;
        return apiClient(original);
      }
      clearSession();
    }
    if (err.response?.status === 429) {
      message.warning('请求过于频繁，请稍后再试');
    }
    return Promise.reject(err);
  }
);

export default apiClient;
