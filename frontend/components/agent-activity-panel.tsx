'use client';

import Link from 'next/link';
import { ArrowRight, Radar, Rss } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { EventCard } from '@/components/event-card';
import { ErrorState } from '@/components/error-state';
import { EmptyState } from '@/components/empty-state';
import { UnavailableState } from '@/components/unavailable-state';
import { NotConfiguredState, UnauthorizedState } from '@/components/events-feed';
import { useAgentEvents } from '@/lib/use-agent-events';

/** Compact "Agent Activity" panel for the dashboard: latest 5 detector events. */
export function AgentActivityPanel({ limit = 5 }: { limit?: number }) {
  const { result, error, loading, refresh } = useAgentEvents({ limit }, 10000);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="flex items-center gap-2">
          <Radar className="h-4 w-4 text-zinc-500" /> Agent activity
        </CardTitle>
        <Link
          href="/events"
          className="flex items-center gap-1 text-[11px] font-medium text-zinc-400 hover:text-zinc-100"
        >
          View all <ArrowRight className="h-3 w-3" />
        </Link>
      </CardHeader>
      <CardContent className="space-y-2">
        {loading && !result ? (
          Array.from({ length: 3 }, (_, i) => <Skeleton key={i} className="h-14 w-full" />)
        ) : error && !result ? (
          <ErrorState error={error} onRetry={refresh} compact />
        ) : !result ? null : !result.configured ? (
          <NotConfiguredState compact />
        ) : 'error' in result ? (
          result.error === 'unauthorized' ? (
            <UnauthorizedState compact />
          ) : (
            <UnavailableState reason="The agent event stream is currently unavailable." />
          )
        ) : result.events.length === 0 ? (
          <EmptyState
            title="No events yet"
            description="Detectors publish as conditions trigger."
            icon={<Rss className="h-6 w-6" />}
            className="p-4"
          />
        ) : (
          result.events.map((event) => <EventCard key={event.id} event={event} compact />)
        )}
      </CardContent>
    </Card>
  );
}
