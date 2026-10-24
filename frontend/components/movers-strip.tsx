'use client';

import Link from 'next/link';
import { Flame, TrendingDown, TrendingUp } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { ChangeBadge } from '@/components/change-badge';
import { ErrorState } from '@/components/error-state';
import { EmptyState } from '@/components/empty-state';
import { UnavailableState } from '@/components/unavailable-state';
import { usePolling } from '@/lib/use-polling';
import type { CoinSummary, ListResponse } from '@/lib/api';
import { formatUSD } from '@/lib/format';

function MoverList({ type, title, icon }: { type: 'gainers' | 'losers' | 'volume'; title: string; icon: React.ReactNode }) {
  const { data, error, loading, refresh } = usePolling<ListResponse<CoinSummary>>(
    `/market/movers?type=${type}&limit=5`,
    60000,
  );

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2">{icon} {title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1.5">
        {loading && !data ? (
          Array.from({ length: 5 }, (_, i) => <Skeleton key={i} className="h-7 w-full" />)
        ) : error && !data ? (
          <ErrorState error={error} onRetry={refresh} compact />
        ) : !data ? null : !data.meta.available ? (
          <UnavailableState className="p-3" />
        ) : data.items.length === 0 ? (
          <EmptyState title="No movers" className="p-3" />
        ) : (
          data.items.map((c) => (
            <Link
              key={c.id}
              href={`/crypto/${encodeURIComponent(c.symbol)}`}
              className="flex items-center justify-between rounded-md px-2 py-1.5 hover:bg-zinc-800/50"
            >
              <span className="flex items-center gap-2">
                {c.image ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={c.image} alt={c.symbol} className="h-4 w-4 rounded-full" loading="lazy" />
                ) : (
                  <span className="h-4 w-4 rounded-full bg-zinc-800" />
                )}
                <span className="text-xs font-medium text-zinc-200">{c.symbol}</span>
              </span>
              <span className="flex items-center gap-3 text-xs">
                {type === 'volume' ? (
                  <span className="tabular text-zinc-400">{formatUSD(c.volume_24h)}</span>
                ) : (
                  <ChangeBadge value={c.change_24h} showIcon={false} />
                )}
                <span className="tabular text-zinc-500">{formatUSD(c.price)}</span>
              </span>
            </Link>
          ))
        )}
      </CardContent>
    </Card>
  );
}

export function MoversStrip() {
  return (
    <div className="grid gap-4 md:grid-cols-3">
      <MoverList type="gainers" title="Top gainers" icon={<TrendingUp className="h-4 w-4 text-emerald-400" />} />
      <MoverList type="losers" title="Top losers" icon={<TrendingDown className="h-4 w-4 text-rose-400" />} />
      <MoverList type="volume" title="Volume leaders" icon={<Flame className="h-4 w-4 text-amber-400" />} />
    </div>
  );
}
