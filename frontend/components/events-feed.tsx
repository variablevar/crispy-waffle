'use client';

import { useState } from 'react';
import { KeyRound, Rss, ShieldAlert } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { EventCard } from '@/components/event-card';
import { ErrorState } from '@/components/error-state';
import { EmptyState } from '@/components/empty-state';
import { UnavailableState } from '@/components/unavailable-state';
import { DataFreshness } from '@/components/data-freshness';
import { AGENT_EVENT_TYPES, useAgentEvents } from '@/lib/use-agent-events';
import type { AgentEventSeverity } from '@/lib/agent-api';

const SEVERITIES: AgentEventSeverity[] = ['info', 'warning', 'critical'];
const PAGE_LIMIT = 50;

export function NotConfiguredState({ compact = false }: { compact?: boolean }) {
  return (
    <EmptyState
      title="Agent feed not configured"
      description="Set AGENT_API_KEY on the frontend server to enable the agent feed."
      icon={<KeyRound className={compact ? 'h-4 w-4' : 'h-6 w-6'} />}
      className={compact ? 'p-4' : undefined}
    />
  );
}

export function UnauthorizedState({ compact = false }: { compact?: boolean }) {
  return (
    <EmptyState
      title="Agent API key rejected"
      description="The backend returned 401/403 for the configured AGENT_API_KEY. Check the key and its read scope."
      icon={<ShieldAlert className={compact ? 'h-4 w-4' : 'h-6 w-6'} />}
      className={compact ? 'p-4' : undefined}
    />
  );
}

export function EventsFeed() {
  const [severity, setSeverity] = useState<string>('');
  const [type, setType] = useState<string>('');
  const [asset, setAsset] = useState<string>('');

  const { result, error, loading, refresh } = useAgentEvents(
    {
      limit: PAGE_LIMIT,
      severity: severity || undefined,
      type: type || undefined,
      asset: asset.trim() ? asset.trim().toUpperCase() : undefined,
    },
    10000,
  );

  return (
    <div className="space-y-4">
      {/* filters */}
      <Card>
        <CardContent className="flex flex-wrap items-center gap-3 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <button onClick={() => setSeverity('')}>
              <Badge variant={severity === '' ? 'info' : 'outline'} className="cursor-pointer">all severities</Badge>
            </button>
            {SEVERITIES.map((s) => (
              <button key={s} onClick={() => setSeverity(s)}>
                <Badge variant={severity === s ? 'info' : 'outline'} className="cursor-pointer">{s}</Badge>
              </button>
            ))}
          </div>
          <Select value={type} onChange={(e) => setType(e.target.value)} className="w-60">
            <option value="">all event types</option>
            {AGENT_EVENT_TYPES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </Select>
          <Input
            value={asset}
            onChange={(e) => setAsset(e.target.value)}
            placeholder="Filter by asset (e.g. BTC)"
            className="w-48"
          />
          {result?.configured && 'events' in result && (
            <span className="ml-auto">
              <DataFreshness updatedAt={result.processedAt} stale={result.stale} />
            </span>
          )}
        </CardContent>
      </Card>

      {/* feed */}
      {loading && !result ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }, (_, i) => <Skeleton key={i} className="h-20 w-full" />)}
        </div>
      ) : error && !result ? (
        <ErrorState error={error} onRetry={refresh} />
      ) : !result ? null : !result.configured ? (
        <NotConfiguredState />
      ) : 'error' in result ? (
        result.error === 'unauthorized' ? (
          <UnauthorizedState />
        ) : (
          <UnavailableState reason="The agent event stream is currently unavailable. No events are shown to avoid displaying fabricated data." />
        )
      ) : result.events.length === 0 ? (
        <EmptyState
          title="No events yet"
          description="No events yet — detectors publish as conditions trigger."
          icon={<Rss className="h-6 w-6" />}
        />
      ) : (
        <div className="space-y-2">
          {result.events.map((event) => (
            <EventCard key={event.id} event={event} />
          ))}
        </div>
      )}
    </div>
  );
}
