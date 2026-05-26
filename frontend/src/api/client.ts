import axios from 'axios';

const apiClient = axios.create({
  baseURL: '/api',
  timeout: 120000,
  headers: { 'Content-Type': 'application/json' },
});

apiClient.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 429) {
      console.error('请求过于频繁，请稍后再试');
    }
    return Promise.reject(err);
  }
);

export default apiClient;
