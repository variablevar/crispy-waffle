'use client';

import { useRouter } from 'next/navigation';
import { Newspaper } from 'lucide-react';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { ChangeBadge } from '@/components/change-badge';
import { TrendBadge } from '@/components/trend-badge';
import { Sparkline } from '@/components/sparkline';
import { DataFreshness } from '@/components/data-freshness';
import { ErrorState } from '@/components/error-state';
import { EmptyState } from '@/components/empty-state';
import { UnavailableState } from '@/components/unavailable-state';
import { usePolling } from '@/lib/use-polling';
import type { CoinSummary, ListResponse } from '@/lib/api';
import { formatUSD } from '@/lib/format';
import { cn } from '@/lib/utils';

function SentimentBadge({ sentiment }: { sentiment: CoinSummary['sentiment'] }) {
  if (!sentiment) return <span className="text-zinc-600">—</span>;
  const variant = sentiment.score > 0.1 ? 'success' : sentiment.score < -0.1 ? 'destructive' : 'warning';
  return <Badge variant={variant}>{sentiment.label}</Badge>;
}

/** Shared market table (top by market cap / top by volume). */
export function CoinTable({ url, pollMs = 60000 }: { url: string; pollMs?: number }) {
  const router = useRouter();
  const { data, error, loading, refresh } = usePolling<ListResponse<CoinSummary>>(url, pollMs);

  if (loading && !data) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 8 }, (_, i) => (
          <Skeleton key={i} className="h-11 w-full" />
        ))}
      </div>
    );
  }
  if (error && !data) return <ErrorState error={error} onRetry={refresh} />;
  if (!data) return null;
  if (!data.meta.available) return <UnavailableState />;
  if (data.items.length === 0) return <EmptyState title="No coins returned" />;

  return (
    <div>
      <div className="mb-2 flex items-center justify-end gap-2">
        {error && <span className="text-[11px] text-rose-400">refresh failed</span>}
        <DataFreshness updatedAt={data.meta.updated_at} stale={data.meta.stale} available={data.meta.available} />
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-8">#</TableHead>
            <TableHead>Coin</TableHead>
            <TableHead className="text-right">Price</TableHead>
            <TableHead className="text-right">1h</TableHead>
            <TableHead className="text-right">24h</TableHead>
            <TableHead className="text-right">7d</TableHead>
            <TableHead className="text-right">Market cap</TableHead>
            <TableHead className="text-right">Volume 24h</TableHead>
            <TableHead className="text-right">Dom.</TableHead>
            <TableHead>7d trend</TableHead>
            <TableHead>Trend</TableHead>
            <TableHead>Sentiment</TableHead>
            <TableHead className="text-right">News 24h</TableHead>
            <TableHead>Fresh</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.items.map((coin, i) => (
            <TableRow
              key={coin.id}
              className="cursor-pointer"
              onClick={() => router.push(`/crypto/${encodeURIComponent(coin.symbol)}`)}
            >
              <TableCell className="text-zinc-500">{i + 1}</TableCell>
              <TableCell>
                <span className="flex items-center gap-2">
                  {coin.image ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={coin.image} alt={coin.symbol} className="h-5 w-5 rounded-full" loading="lazy" />
                  ) : (
                    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-zinc-800 text-[9px] font-bold text-zinc-400">
                      {coin.symbol.slice(0, 2)}
                    </span>
                  )}
                  <span className="font-medium text-zinc-100">{coin.name}</span>
                  <span className="text-[11px] uppercase text-zinc-500">{coin.symbol}</span>
                </span>
              </TableCell>
              <TableCell className="text-right font-medium">{formatUSD(coin.price)}</TableCell>
              <TableCell className="text-right"><ChangeBadge value={coin.change_1h} showIcon={false} /></TableCell>
              <TableCell className="text-right"><ChangeBadge value={coin.change_24h} showIcon={false} /></TableCell>
              <TableCell className="text-right"><ChangeBadge value={coin.change_7d} showIcon={false} /></TableCell>
              <TableCell className="text-right">{formatUSD(coin.market_cap)}</TableCell>
              <TableCell className="text-right">{formatUSD(coin.volume_24h)}</TableCell>
              <TableCell className="text-right text-zinc-400">
                {coin.dominance == null ? '—' : `${coin.dominance.toFixed(1)}%`}
              </TableCell>
              <TableCell><Sparkline data={coin.sparkline} /></TableCell>
              <TableCell><TrendBadge trend={coin.trend} /></TableCell>
              <TableCell><SentimentBadge sentiment={coin.sentiment} /></TableCell>
              <TableCell className="text-right">
                <span className={cn('inline-flex items-center gap-1', coin.news_count_24h > 0 ? 'text-zinc-300' : 'text-zinc-600')}>
                  <Newspaper className="h-3 w-3" />
                  {coin.news_count_24h}
                </span>
              </TableCell>
              <TableCell>
                <DataFreshness updatedAt={coin.updated_at} stale={coin.stale} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
