'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch } from './api';

export interface PollingResult<T> {
  data: T | null;
  error: string | null;
  loading: boolean; // true only until the first successful/failed fetch
  lastFetchedAt: number | null;
  refresh: () => void;
}

/**
 * SWR-lite polling hook. Fetches `path` (relative to /api/v1) immediately and
 * then every `intervalMs`. Pass `null` path to disable. intervalMs <= 0 fetches once.
 */
export function usePolling<T>(path: string | null, intervalMs: number): PollingResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastFetchedAt, setLastFetchedAt] = useState<number | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const load = useCallback(
    async (showSpinner = false) => {
      if (!path) return;
      if (showSpinner) setLoading(true);
      try {
        const d = await apiFetch<T>(path);
        if (!mounted.current) return;
        setData(d);
        setError(null);
        setLastFetchedAt(Date.now());
      } catch (e) {
        if (!mounted.current) return;
        setError(e instanceof Error ? e.message : 'Request failed');
      } finally {
        if (mounted.current) setLoading(false);
      }
    },
    [path],
  );

  useEffect(() => {
    setData(null);
    setError(null);
    setLoading(true);
    load();
    if (!path || intervalMs <= 0) return;
    const id = setInterval(() => load(), intervalMs);
    return () => clearInterval(id);
  }, [load, intervalMs, path]);

  return { data, error, loading, lastFetchedAt, refresh: () => void load() };
}
