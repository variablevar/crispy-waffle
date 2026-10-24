import type { Metadata } from 'next';
import { Radar } from 'lucide-react';
import { EventsFeed } from '@/components/events-feed';

export const metadata: Metadata = {
  title: 'Agent Events — SkyBus',
  description: 'Machine-grade market events published by the SkyBus detectors',
};

export const dynamic = 'force-dynamic';

export default function EventsPage() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="flex items-center gap-2 text-lg font-bold text-zinc-100">
          <Radar className="h-5 w-5 text-zinc-500" /> Agent events
        </h1>
        <p className="text-xs text-zinc-500">
          Detector events from the SkyBus agent API — auto-refreshes every 10s
        </p>
      </div>
      <EventsFeed />
    </div>
  );
}
