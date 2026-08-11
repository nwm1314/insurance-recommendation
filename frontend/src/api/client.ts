import axios, { InternalAxiosRequestConfig } from 'axios';
import { message } from 'antd';

const apiClient = axios.create({
  baseURL: '/api',
  timeout: 120000,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
});

function clearSession() {
  localStorage.removeItem('auth_user');
  window.dispatchEvent(new Event('auth-changed'));
}

apiClient.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config as (InternalAxiosRequestConfig & { _retried?: boolean }) | undefined;
    const url = original?.url ?? '';
    const isAuthEndpoint = url === '/auth/login' || url === '/auth/register';
    if (err.response?.status === 401 && original && !original._retried && !isAuthEndpoint) {
      original._retried = true;
      try {
        await axios.post('/api/auth/refresh', {}, { withCredentials: true });
        return apiClient(original);
      } catch {
        clearSession();
        window.location.href = '/login';
      }
    }
    if (err.response?.status === 429) {
      message.warning('请求过于频繁，请稍后再试');
    }
    return Promise.reject(err);
  }
);

export default apiClient;