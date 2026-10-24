'use client';

import { ChangeBadge } from '@/components/change-badge';
import { TrendBadge } from '@/components/trend-badge';
import { DataFreshness } from '@/components/data-freshness';
import { Skeleton } from '@/components/ui/skeleton';
import { usePolling } from '@/lib/use-polling';
import type { CoinDetail } from '@/lib/api';
import { formatUSD } from '@/lib/format';

/** Sticky coin header with live-polling price. */
export function CoinHeader({ symbol }: { symbol: string }) {
  const { data } = usePolling<CoinDetail>(`/coins/${encodeURIComponent(symbol)}`, 5000);

  return (
    <div className="sticky top-12 z-20 -mx-4 border-b border-zinc-800 bg-background/95 px-4 py-3 backdrop-blur md:-mx-6 md:px-6">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        {data ? (
          <>
            <span className="flex items-center gap-2.5">
              {data.image ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={data.image} alt={data.symbol} className="h-8 w-8 rounded-full" />
              ) : (
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-zinc-800 text-xs font-bold text-zinc-400">
                  {data.symbol.slice(0, 2)}
                </span>
              )}
              <span>
                <span className="block text-sm font-bold leading-tight text-zinc-100">{data.name}</span>
                <span className="block text-[11px] uppercase leading-tight text-zinc-500">{data.symbol}</span>
              </span>
            </span>
            <span className="text-xl font-bold tabular text-zinc-100">{formatUSD(data.price)}</span>
            <span className="flex items-center gap-2 text-xs">
              <span className="text-zinc-500">1h</span><ChangeBadge value={data.change_1h} />
              <span className="text-zinc-500">24h</span><ChangeBadge value={data.change_24h} />
              <span className="text-zinc-500">7d</span><ChangeBadge value={data.change_7d} />
            </span>
            <TrendBadge trend={data.trend} />
            <span className="ml-auto">
              <DataFreshness updatedAt={data.updated_at} stale={data.stale} />
            </span>
          </>
        ) : (
          <>
            <Skeleton className="h-8 w-40" />
            <Skeleton className="h-8 w-28" />
          </>
        )}
      </div>
    </div>
  );
}
