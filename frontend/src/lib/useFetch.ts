import { useState, useEffect, useCallback, useRef } from 'react';
import { ApiError } from './api';

export interface UseFetchResult<T> {
  data: T | null;
  loading: boolean;
  error: ApiError | Error | null;
  refetch: () => void;
  setData: React.Dispatch<React.SetStateAction<T | null>>;
}

/**
 * Hook fetch sederhana dengan AbortController untuk membatalkan request lama.
 */
export function useFetch<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  deps: unknown[] = [],
  enabled: boolean = true
): UseFetchResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState<boolean>(enabled);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [refetchIndex, setRefetchIndex] = useState(0);

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const refetch = useCallback(() => {
    setRefetchIndex((prev) => prev + 1);
  }, []);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }

    const controller = new AbortController();
    let isCancelled = false;

    // Menghindari cascading render dengan asynchronous microtask
    queueMicrotask(() => {
      if (!isCancelled) {
        setLoading(true);
        setError(null);
      }
    });

    fetcherRef.current(controller.signal)
      .then((result) => {
        if (!isCancelled) {
          setData(result);
          setLoading(false);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (isCancelled || controller.signal.aborted) {
          return;
        }
        if (err instanceof DOMException && err.name === 'AbortError') {
          return;
        }
        if (err instanceof Error && err.name === 'AbortError') {
          return;
        }

        const normalizedError = err instanceof Error ? err : new ApiError(0, String(err));
        setError(normalizedError);
        setLoading(false);
      });

    return () => {
      isCancelled = true;
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, refetchIndex, enabled]);

  return { data, loading, error, refetch, setData };
}
