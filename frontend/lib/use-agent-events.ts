'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { AgentEventType, AgentEventsResult } from './agent-api';

/** The 16 event types from docs/AGENT_CONTRACT.md, kept in sync via the type check below. */
export const AGENT_EVENT_TYPES = [
  'PRICE_LEVEL_CROSSED',
  'LIQUIDITY_ZONE_APPROACH',
  'LIQUIDITY_ZONE_BREACHED',
  'LIQUIDITY_SWEEP_DETECTED',
  'CVD_DIVERGENCE',
  'OPEN_INTEREST_SPIKE',
  'FUNDING_EXTREME',
  'LONG_LIQUIDATION_BURST',
  'SHORT_LIQUIDATION_BURST',
  'CROSS_EXCHANGE_DIVERGENCE',
  'NEWS_BREAKING',
  'MARKET_REGIME_CHANGED',
  'SCENARIO_CREATED',
  'SCENARIO_INVALIDATED',
  'DATA_STALE',
  'DATA_RECOVERED',
] as const satisfies readonly AgentEventType[];

export interface AgentEventsClientQuery {
  limit?: number;
  severity?: string;
  type?: string;
  asset?: string;
}

/** Browser-side URL for the route handler — the API key never leaves the server. */
export function agentEventsUrl(q: AgentEventsClientQuery): string {
  const params = new URLSearchParams();
  params.set('limit', String(q.limit ?? 50));
  if (q.severity) params.set('severity', q.severity);
  if (q.type) params.set('type', q.type);
  if (q.asset) params.set('asset', q.asset);
  return `/api/agent-events?${params.toString()}`;
}

export interface AgentEventsPoll {
  result: AgentEventsResult | null;
  error: string | null;
  loading: boolean; // true only until the first successful/failed fetch
  refresh: () => void;
}

/** Polls the /api/agent-events route handler. Same shape/semantics as usePolling. */
export function useAgentEvents(q: AgentEventsClientQuery, intervalMs = 10000): AgentEventsPoll {
  const [result, setResult] = useState<AgentEventsResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const mounted = useRef(true);
  const url = agentEventsUrl(q);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const load = useCallback(
    async (showSpinner = false) => {
      if (showSpinner) setLoading(true);
      try {
        const res = await fetch(url, { cache: 'no-store' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as AgentEventsResult;
        if (!mounted.current) return;
        setResult(data);
        setError(null);
      } catch (e) {
        if (!mounted.current) return;
        setError(e instanceof Error ? e.message : 'Request failed');
      } finally {
        if (mounted.current) setLoading(false);
      }
    },
    [url],
  );

  useEffect(() => {
    setResult(null);
    setError(null);
    setLoading(true);
    load();
    if (intervalMs <= 0) return;
    const id = setInterval(() => load(), intervalMs);
    return () => clearInterval(id);
  }, [load, intervalMs]);

  return { result, error, loading, refresh: () => void load() };
}
