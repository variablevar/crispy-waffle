// SERVER-SIDE ONLY fetcher for the SkyBus agent API (docs/AGENT_CONTRACT.md).
// Reads AGENT_API_KEY from the frontend server environment. Never expose this
// module to client components and never move the key to a NEXT_PUBLIC_* var —
// browser code must go through the /api/agent-events route handler instead.

export type AgentEventSeverity = 'info' | 'warning' | 'critical';

export type AgentEventType =
  | 'PRICE_LEVEL_CROSSED'
  | 'LIQUIDITY_ZONE_APPROACH'
  | 'LIQUIDITY_ZONE_BREACHED'
  | 'LIQUIDITY_SWEEP_DETECTED'
  | 'CVD_DIVERGENCE'
  | 'OPEN_INTEREST_SPIKE'
  | 'FUNDING_EXTREME'
  | 'LONG_LIQUIDATION_BURST'
  | 'SHORT_LIQUIDATION_BURST'
  | 'CROSS_EXCHANGE_DIVERGENCE'
  | 'NEWS_BREAKING'
  | 'MARKET_REGIME_CHANGED'
  | 'SCENARIO_CREATED'
  | 'SCENARIO_INVALIDATED'
  | 'DATA_STALE'
  | 'DATA_RECOVERED';

export interface AgentEventEvidence {
  indicator: string;
  value: string;
  supports: boolean;
}

export interface AgentEvent {
  specversion: string;
  id: string;
  type: AgentEventType;
  source: string;
  time: string;
  published_at: string;
  asset: string | null;
  venue: string | null;
  instrument: string | null;
  severity: AgentEventSeverity;
  confidence: number | null;
  summary: string;
  evidence: AgentEventEvidence[];
  measurements: {
    observed: Record<string, unknown>;
    estimated: Record<string, unknown>;
  };
  methodology_version?: string | null;
  idempotency_key: string;
  scenario_id: string | null;
  stream_id: string | null;
}

export interface AgentEventsQuery {
  limit?: number;
  type?: string;
  asset?: string;
  severity?: string;
}

/**
 * Discriminated result so the UI can distinguish "feed disabled" (missing key —
 * a friendly empty state, NOT an error) from auth failures and real outages.
 */
export type AgentEventsResult =
  | { configured: false }
  | { configured: true; error: 'unauthorized' | 'unavailable' }
  | {
      configured: true;
      events: AgentEvent[];
      stale: boolean;
      observedAt: string | null;
      processedAt: string | null;
    };

interface AgentEnvelope {
  available?: boolean;
  stale?: boolean;
  observed_at?: string | null;
  processed_at?: string | null;
  data?: { items?: unknown; next_cursor?: string | null };
}

export async function getAgentEvents(q: AgentEventsQuery = {}): Promise<AgentEventsResult> {
  const apiKey = process.env.AGENT_API_KEY;
  if (!apiKey) return { configured: false };

  const base = process.env.BACKEND_INTERNAL_URL || 'http://localhost:8000';
  const params = new URLSearchParams();
  const limit = Math.min(Math.max(Math.trunc(q.limit ?? 50) || 50, 1), 200);
  params.set('limit', String(limit));
  if (q.type) params.set('type', q.type);
  if (q.asset) params.set('asset', q.asset.trim().toUpperCase());
  if (q.severity) params.set('severity', q.severity);

  try {
    const res = await fetch(`${base}/api/v1/agent/events?${params.toString()}`, {
      headers: { 'X-API-Key': apiKey, Accept: 'application/json' },
      cache: 'no-store',
    });
    if (res.status === 401 || res.status === 403) return { configured: true, error: 'unauthorized' };
    if (!res.ok) return { configured: true, error: 'unavailable' };

    const envelope = (await res.json()) as AgentEnvelope;
    if (envelope.available === false) return { configured: true, error: 'unavailable' };
    const items = envelope.data?.items;
    if (!Array.isArray(items)) return { configured: true, error: 'unavailable' };

    return {
      configured: true,
      events: items as AgentEvent[],
      stale: Boolean(envelope.stale),
      observedAt: envelope.observed_at ?? null,
      processedAt: envelope.processed_at ?? null,
    };
  } catch {
    return { configured: true, error: 'unavailable' };
  }
}
