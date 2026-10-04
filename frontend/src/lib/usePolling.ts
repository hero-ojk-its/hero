import { useState, useEffect, useRef, useCallback } from 'react';

export interface UsePollingOptions<T> {
  /** Fungsi pemanggilan API yang menerima AbortSignal */
  fn: (signal: AbortSignal) => Promise<T>;
  /** Predikat penentu apakah data telah mencapai status terminal (selesai, gagal, dibatalkan) */
  isTerminal: (data: T) => boolean;
  /** Interval polling dalam milidetik (default: 2000 ms) */
  interval?: number;
  /** Batas durasi maksimum polling dalam milidetik (default: 600.000 ms / 10 menit) */
  maxDuration?: number;
  /** Apakah polling sedang aktif (default: true) */
  enabled?: boolean;
  /** Callback saat data mencapai status terminal */
  onSuccess?: (data: T) => void;
  /** Callback saat polling gagal mencapai terminal atau galat fatal */
  onError?: (error: Error) => void;
  /** Batas galat beruntun sebelum menampilkan ErrorState (default: 3) */
  maxConsecutiveErrors?: number;
}

export interface UsePollingResult<T> {
  data: T | null;
  isLoading: boolean;
  isPolling: boolean;
  isTerminal: boolean;
  error: Error | null;
  consecutiveErrors: number;
  retry: () => void;
  stop: () => void;
}

export function usePolling<T>({
  fn,
  isTerminal,
  interval = 2000,
  maxDuration = 600000,
  enabled = true,
  onSuccess,
  onError,
  maxConsecutiveErrors = 3,
}: UsePollingOptions<T>): UsePollingResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(enabled);
  const [isPolling, setIsPolling] = useState<boolean>(enabled);
  const [isTerminalState, setIsTerminalState] = useState<boolean>(false);
  const [error, setError] = useState<Error | null>(null);
  const [consecutiveErrors, setConsecutiveErrors] = useState<number>(0);

  const abortControllerRef = useRef<AbortController | null>(null);
  const timerIdRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const startTimeRef = useRef<number>(0);
  const consecutiveErrorsRef = useRef<number>(0);
  const isStoppedRef = useRef<boolean>(!enabled);

  // Keep latest function callbacks in refs to avoid restarting effect unnecessarily
  const fnRef = useRef(fn);
  const isTerminalRef = useRef(isTerminal);
  const onSuccessRef = useRef(onSuccess);
  const onErrorRef = useRef(onError);

  useEffect(() => {
    fnRef.current = fn;
    isTerminalRef.current = isTerminal;
    onSuccessRef.current = onSuccess;
    onErrorRef.current = onError;
  });

  const cleanup = useCallback(() => {
    if (timerIdRef.current) {
      clearTimeout(timerIdRef.current);
      timerIdRef.current = null;
    }
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }, []);

  const stop = useCallback(() => {
    isStoppedRef.current = true;
    cleanup();
    setIsPolling(false);
    setIsLoading(false);
  }, [cleanup]);

  const executePollRef = useRef<() => Promise<void>>(async () => {});

  const executePoll = useCallback(async () => {
    if (isStoppedRef.current) return;

    if (startTimeRef.current === 0) {
      startTimeRef.current = Date.now();
    }

    // Cek batas waktu maksimum
    if (Date.now() - startTimeRef.current > maxDuration) {
      const timeoutErr = new Error(`Proses pemindaian melebihi batas waktu maksimum (${Math.round(maxDuration / 1000)} detik).`);
      setError(timeoutErr);
      setIsPolling(false);
      setIsLoading(false);
      onErrorRef.current?.(timeoutErr);
      return;
    }

    // Buat controller baru per pemanggilan
    cleanup();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const result = await fnRef.current(controller.signal);
      if (isStoppedRef.current) return;

      setData(result);
      setError(null);
      consecutiveErrorsRef.current = 0;
      setConsecutiveErrors(0);
      setIsLoading(false);

      if (isTerminalRef.current(result)) {
        setIsTerminalState(true);
        setIsPolling(false);
        onSuccessRef.current?.(result);
        return;
      }

      // Jadwalkan polling berikutnya lewat ref untuk menghindari capture saat inisialisasi
      timerIdRef.current = setTimeout(() => {
        void executePollRef.current();
      }, interval);
    } catch (err: unknown) {
      if (isStoppedRef.current) return;
      if (err instanceof DOMException && err.name === 'AbortError') {
        return;
      }
      if (err instanceof Error && err.name === 'AbortError') {
        return;
      }

      consecutiveErrorsRef.current += 1;
      const count = consecutiveErrorsRef.current;
      setConsecutiveErrors(count);

      if (count >= maxConsecutiveErrors) {
        const errorObj = err instanceof Error ? err : new Error(String(err));
        setError(errorObj);
        setIsPolling(false);
        setIsLoading(false);
        onErrorRef.current?.(errorObj);
      } else {
        // Jeda bertahap (stepped backoff)
        const delay = Math.min(interval * Math.pow(1.5, count), 10000);
        timerIdRef.current = setTimeout(() => {
          void executePollRef.current();
        }, delay);
      }
    }
  }, [cleanup, interval, maxDuration, maxConsecutiveErrors]);

  useEffect(() => {
    executePollRef.current = executePoll;
  });

  const retry = useCallback(() => {
    isStoppedRef.current = false;
    consecutiveErrorsRef.current = 0;
    setConsecutiveErrors(0);
    setError(null);
    setIsLoading(true);
    setIsPolling(true);
    setIsTerminalState(false);
    startTimeRef.current = Date.now();
    void executePoll();
  }, [executePoll]);

  useEffect(() => {
    if (enabled) {
      isStoppedRef.current = false;
      startTimeRef.current = Date.now();
      void executePoll();
    } else {
      isStoppedRef.current = true;
      cleanup();
      void Promise.resolve().then(() => {
        setIsPolling(false);
        setIsLoading(false);
      });
    }

    return () => {
      cleanup();
    };
  }, [enabled, executePoll, cleanup]);

  return {
    data,
    isLoading,
    isPolling,
    isTerminal: isTerminalState,
    error,
    consecutiveErrors,
    retry,
    stop,
  };
}
