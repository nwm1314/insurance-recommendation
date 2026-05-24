import { useRef, useCallback } from 'react';

export function useSSE() {
  const controllerRef = useRef<AbortController | null>(null);

  const abort = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
  }, []);

  const setController = useCallback((c: AbortController) => {
    controllerRef.current = c;
  }, []);

  return { abort, setController };
}
