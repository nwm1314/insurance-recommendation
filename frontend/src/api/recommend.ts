import apiClient from './client';
import type { UserProfile, RecommendationResult } from '../types';

export async function fetchRecommend(userProfile: UserProfile): Promise<RecommendationResult> {
  const { data } = await apiClient.post<RecommendationResult>('/recommend', userProfile);
  return data;
}

export function fetchRecommendSSE(
  userProfile: UserProfile,
  onData: (result: RecommendationResult) => void,
  onDone: () => void,
  onError: (err: Error) => void,
): AbortController {
  const controller = new AbortController();
  const token = localStorage.getItem('access_token');
  fetch('/api/recommend', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(userProfile),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const content = line.slice(6);
            if (content === '[DONE]') { onDone(); return; }
            try {
              const result = JSON.parse(content) as RecommendationResult;
              onData(result);
            } catch { /* ignore partial chunk */ }
          }
        }
      }
      onDone();
    })
    .catch((err) => {
      if (err.name !== 'AbortError') onError(err);
    });
  return controller;
}
