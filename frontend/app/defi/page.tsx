'use client';

import { Droplets, ExternalLink, Info } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { ChangeBadge } from '@/components/change-badge';
import { DataFreshness } from '@/components/data-freshness';
import { ErrorState } from '@/components/error-state';
import { EmptyState } from '@/components/empty-state';
import { usePolling } from '@/lib/use-polling';
import type { CoinSummary, DefiResponse, ListResponse } from '@/lib/api';
import { formatUSD } from '@/lib/format';

function DefiCoinSection({ symbol }: { symbol: string }) {
  const { data, error, loading, refresh } = usePolling<DefiResponse>(
    `/coins/${encodeURIComponent(symbol)}/defi`,
    60000,
  );

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="flex items-center gap-2">
          {symbol}
          {data?.tvl_usd != null && (
            <span className="text-[11px] font-normal text-zinc-500">
              pool liquidity <span className="tabular text-zinc-300">{formatUSD(data.tvl_usd)}</span>
            </span>
          )}
        </CardTitle>
        {data && <DataFreshness updatedAt={data.updated_at} stale={data.stale} />}
      </CardHeader>
      <CardContent>
        {loading && !data ? (
          <Skeleton className="h-24 w-full" />
        ) : error && !data ? (
          <ErrorState error={error} onRetry={refresh} compact />
        ) : !data ? null : data.pools.length === 0 ? (
          <EmptyState title={`No tracked pools for ${symbol}`} className="p-4" />
        ) : (
          <>
            {data.source.length > 0 && (
              <p className="mb-2 text-[10px] text-zinc-600">source: {data.source.join(', ')}</p>
            )}
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Chain</TableHead>
                  <TableHead>DEX</TableHead>
                  <TableHead>Pair</TableHead>
                  <TableHead className="text-right">Liquidity</TableHead>
                  <TableHead className="text-right">Volume 24h</TableHead>
                  <TableHead className="text-right">Price</TableHead>
                  <TableHead className="text-right">24h</TableHead>
                  <TableHead className="w-8" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.pools.map((p, i) => (
                  <TableRow key={i}>
                    <TableCell><Badge variant="outline">{p.chain}</Badge></TableCell>
                    <TableCell className="text-zinc-300">{p.dex}</TableCell>
                    <TableCell className="font-medium text-zinc-100">{p.pair}</TableCell>
                    <TableCell className="text-right">{formatUSD(p.liquidity_usd)}</TableCell>
                    <TableCell className="text-right">{formatUSD(p.volume_24h)}</TableCell>
                    <TableCell className="text-right">{formatUSD(p.price_usd)}</TableCell>
                    <TableCell className="text-right"><ChangeBadge value={p.price_change_24h} showIcon={false} /></TableCell>
                    <TableCell>
                      {p.url && (
                        <a href={p.url} target="_blank" rel="noopener noreferrer" className="text-zinc-500 hover:text-zinc-200" aria-label="Open pool">
                          <ExternalLink className="h-3.5 w-3.5" />
                        </a>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </>
        )}
      </CardContent>
    </Card>
  );
}

export default function DefiPage() {
  const { data, error, loading, refresh } = usePolling<ListResponse<CoinSummary>>('/market/top?limit=10', 60000);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="flex items-center gap-2 text-lg font-bold text-zinc-100">
          <Droplets className="h-5 w-5 text-zinc-500" /> DeFi liquidity
        </h1>
        <p className="text-xs text-zinc-500">Tracked AMM pools for the top assets</p>
      </div>

      <div className="flex items-start gap-2 rounded-lg border border-zinc-800 bg-panel-2/50 p-3">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-zinc-500" />
        <p className="text-[11px] leading-relaxed text-zinc-500">
          AMM pool liquidity shown here is distinct from CEX order-book liquidity: pools hold token pairs in a
          contract and quote prices via a curve, while order-book walls/zones (see each coin&apos;s Liquidity tab)
          reflect resting limit orders on centralized exchanges.
        </p>
      </div>

      {loading && !data ? (
        <div className="space-y-4">
          {Array.from({ length: 3 }, (_, i) => <Skeleton key={i} className="h-40 w-full" />)}
        </div>
      ) : error && !data ? (
        <ErrorState error={error} onRetry={refresh} />
      ) : !data ? null : !data.meta.available ? (
        <ErrorState error="Market overview unavailable; cannot determine tracked symbols." onRetry={refresh} />
      ) : data.items.length === 0 ? (
        <EmptyState title="No tracked symbols" />
      ) : (
        <div className="space-y-4">
          {data.items.map((c) => (
            <DefiCoinSection key={c.symbol} symbol={c.symbol} />
          ))}
        </div>
      )}
    </div>
  );
}
