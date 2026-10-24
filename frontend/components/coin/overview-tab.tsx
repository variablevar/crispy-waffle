'use client';

import Link from 'next/link';
import { ArrowRight, Droplets, Layers } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { StatCard } from '@/components/stat-card';
import { ErrorState } from '@/components/error-state';
import { EmptyState } from '@/components/empty-state';
import { UnavailableState } from '@/components/unavailable-state';
import { DataFreshness } from '@/components/data-freshness';
import { usePolling } from '@/lib/use-polling';
import type { CoinDetail, DefiResponse, ExchangeTicker, ListResponse, SentimentReport } from '@/lib/api';
import { formatBps, formatFunding, formatNumber, formatPct, formatUSD } from '@/lib/format';
import { cn } from '@/lib/utils';

function KeyStats({ symbol }: { symbol: string }) {
  const { data, error, loading, refresh } = usePolling<CoinDetail>(`/coins/${encodeURIComponent(symbol)}`, 30000);

  if (loading && !data) {
    return (
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        {Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-24 w-full" />)}
      </div>
    );
  }
  if (error && !data) return <ErrorState error={error} onRetry={refresh} />;
  if (!data) return null;

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <StatCard title="Market cap" value={formatUSD(data.market_cap)} footer={data.market_cap_rank != null ? `Rank #${data.market_cap_rank}` : undefined} />
        <StatCard title="24h volume" value={formatUSD(data.total_volume ?? data.volume_24h)} />
        <StatCard title="Circulating supply" value={data.circulating_supply != null ? `${formatNumber(data.circulating_supply, 0)} ${data.symbol}` : '—'} />
        <StatCard title="Dominance" value={data.dominance != null ? `${data.dominance.toFixed(2)}%` : '—'} />
        <StatCard title="ATH" value={formatUSD(data.ath)} footer={data.ath_change_pct != null ? `${formatPct(data.ath_change_pct)} from ATH` : undefined} />
        <StatCard title="ATL" value={formatUSD(data.atl)} />
      </div>
      {data.description && (
        <Card>
          <CardContent className="p-4">
            <p className="line-clamp-4 text-xs leading-relaxed text-zinc-400">{data.description}</p>
            {data.homepage && (
              <a href={data.homepage} target="_blank" rel="noopener noreferrer" className="mt-2 inline-block text-[11px] text-emerald-400 hover:underline">
                {data.homepage}
              </a>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function ExchangeComparison({ symbol }: { symbol: string }) {
  const { data, error, loading, refresh } = usePolling<ListResponse<ExchangeTicker>>(
    `/coins/${encodeURIComponent(symbol)}/tickers`,
    5000,
  );

  const prices = (data?.items ?? []).map((t) => t.price).filter((p): p is number => p != null && p > 0);
  const divergencePct =
    prices.length >= 2 ? ((Math.max(...prices) - Math.min(...prices)) / Math.min(...prices)) * 100 : null;
  const divergent = divergencePct != null && divergencePct > 0.15;

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="flex items-center gap-2">
          Exchange comparison
          {divergent && (
            <Badge variant="warning" title={`max/min price divergence ${divergencePct?.toFixed(3)}%`}>
              divergence {divergencePct?.toFixed(2)}%
            </Badge>
          )}
        </CardTitle>
        {data && <DataFreshness updatedAt={data.meta.updated_at} stale={data.meta.stale} available={data.meta.available} />}
      </CardHeader>
      <CardContent>
        {loading && !data ? (
          <Skeleton className="h-32 w-full" />
        ) : error && !data ? (
          <ErrorState error={error} onRetry={refresh} compact />
        ) : !data ? null : !data.meta.available ? (
          <UnavailableState />
        ) : data.items.length === 0 ? (
          <EmptyState title="No tickers" description="No exchange tickers for this asset." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Exchange</TableHead>
                <TableHead>Instrument</TableHead>
                <TableHead className="text-right">Price</TableHead>
                <TableHead className="text-right">Spread</TableHead>
                <TableHead className="text-right">Funding</TableHead>
                <TableHead className="text-right">Open interest</TableHead>
                <TableHead className="text-right">Volume 24h</TableHead>
                <TableHead>Fresh</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((t) => (
                <TableRow key={`${t.exchange}-${t.instrument}`} className={cn(t.stale && 'opacity-60')}>
                  <TableCell className="font-medium capitalize text-zinc-200">{t.exchange}</TableCell>
                  <TableCell>
                    <Badge variant={t.instrument === 'spot' ? 'default' : 'info'}>
                      {t.instrument === 'spot' ? 'spot' : 'USDT perp'}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right font-medium">{formatUSD(t.price)}</TableCell>
                  <TableCell className="text-right">{formatBps(t.spread_bps)}</TableCell>
                  <TableCell className={cn('text-right', (t.funding_rate ?? 0) > 0 ? 'text-emerald-400' : (t.funding_rate ?? 0) < 0 ? 'text-rose-400' : '')}>
                    {formatFunding(t.funding_rate)}
                  </TableCell>
                  <TableCell className="text-right">
                    {t.open_interest != null ? `${formatNumber(t.open_interest, 4)} ${symbol}` : '—'}
                  </TableCell>
                  <TableCell className="text-right">{formatUSD(t.volume_24h)}</TableCell>
                  <TableCell><DataFreshness updatedAt={t.updated_at} stale={t.stale} /></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

const SENTIMENT_COMPONENTS = ['news', 'momentum', 'volume', 'funding'] as const;

function ComponentBar({ label, value }: { label: string; value: number | null }) {
  const v = value == null ? null : Math.max(-1, Math.min(1, value));
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-[11px]">
        <span className="capitalize text-zinc-400">{label}</span>
        <span className="tabular text-zinc-300">{v == null ? '—' : v.toFixed(2)}</span>
      </div>
      <div className="relative h-1.5 overflow-hidden rounded-full bg-zinc-800">
        <div className="absolute left-1/2 top-0 h-full w-px bg-zinc-600" />
        {v != null && v !== 0 && (
          <div
            className={cn('absolute top-0 h-full', v > 0 ? 'bg-emerald-500' : 'bg-rose-500')}
            style={{ left: v > 0 ? '50%' : `${50 + v * 50}%`, width: `${Math.abs(v) * 50}%` }}
          />
        )}
      </div>
    </div>
  );
}

function SentimentPanel({ symbol }: { symbol: string }) {
  const { data, error, loading, refresh } = usePolling<SentimentReport>(
    `/coins/${encodeURIComponent(symbol)}/sentiment`,
    30000,
  );

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle>Proprietary sentiment</CardTitle>
        {data && <DataFreshness updatedAt={data.updated_at} stale={data.stale} />}
      </CardHeader>
      <CardContent className="space-y-4">
        {loading && !data ? (
          <Skeleton className="h-32 w-full" />
        ) : error && !data ? (
          <ErrorState error={error} onRetry={refresh} compact />
        ) : !data ? null : (
          <>
            <div className="flex items-center gap-3">
              <span
                className={cn(
                  'text-2xl font-bold tabular',
                  data.asset_score == null
                    ? 'text-zinc-500'
                    : data.asset_score > 0.1
                      ? 'text-emerald-400'
                      : data.asset_score < -0.1
                        ? 'text-rose-400'
                        : 'text-amber-400',
                )}
              >
                {data.asset_score == null ? '—' : data.asset_score.toFixed(2)}
              </span>
              <Badge
                variant={
                  data.asset_score == null
                    ? 'default'
                    : data.asset_score > 0.1
                      ? 'success'
                      : data.asset_score < -0.1
                        ? 'destructive'
                        : 'warning'
                }
              >
                {data.label}
              </Badge>
              {data.market_fear_greed && (
                <span className="ml-auto text-[11px] text-zinc-500">
                  Market F&amp;G: <span className="tabular text-zinc-300">{data.market_fear_greed.value}</span>{' '}
                  ({data.market_fear_greed.classification})
                </span>
              )}
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              {SENTIMENT_COMPONENTS.map((k) => (
                <ComponentBar key={k} label={k} value={data.components[k]} />
              ))}
            </div>
            <p className="rounded-md border border-zinc-800 bg-panel-2/60 p-3 text-[11px] leading-relaxed text-zinc-500">
              {data.disclaimer}
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function DefiPreview({ symbol }: { symbol: string }) {
  const { data, error, loading, refresh } = usePolling<DefiResponse>(`/coins/${encodeURIComponent(symbol)}/defi`, 60000);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="flex items-center gap-2">
          <Droplets className="h-4 w-4 text-zinc-500" /> DeFi liquidity
        </CardTitle>
        <div className="flex items-center gap-3">
          {data && <DataFreshness updatedAt={data.updated_at} stale={data.stale} />}
          <Link href="/defi" className="inline-flex items-center gap-1 text-[11px] text-zinc-500 hover:text-zinc-300">
            all pools <ArrowRight className="h-3 w-3" />
          </Link>
        </div>
      </CardHeader>
      <CardContent>
        {loading && !data ? (
          <Skeleton className="h-20 w-full" />
        ) : error && !data ? (
          <ErrorState error={error} onRetry={refresh} compact />
        ) : !data ? null : data.pools.length === 0 ? (
          <EmptyState title="No tracked pools" className="p-4" />
        ) : (
          <div className="space-y-1.5">
            {data.tvl_usd != null && (
              <p className="text-[11px] text-zinc-500">
                Total pool liquidity: <span className="tabular text-zinc-300">{formatUSD(data.tvl_usd)}</span>
              </p>
            )}
            {data.pools.slice(0, 3).map((p, i) => (
              <div key={i} className="flex items-center justify-between rounded-md bg-panel-2/60 px-3 py-2 text-xs">
                <span className="flex items-center gap-2">
                  <Badge variant="outline">{p.chain}</Badge>
                  <span className="text-zinc-300">{p.dex}</span>
                  <span className="font-medium text-zinc-100">{p.pair}</span>
                </span>
                <span className="tabular text-zinc-400">{formatUSD(p.liquidity_usd)}</span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function OverviewTab({ symbol }: { symbol: string }) {
  return (
    <div className="space-y-4">
      <KeyStats symbol={symbol} />
      <div className="grid gap-4 xl:grid-cols-2">
        <ExchangeComparison symbol={symbol} />
        <SentimentPanel symbol={symbol} />
      </div>
      <DefiPreview symbol={symbol} />
      <div className="flex items-center gap-2 text-[11px] text-zinc-600">
        <Layers className="h-3 w-3" />
        DeFi AMM liquidity is distinct from CEX order-book liquidity.
      </div>
    </div>
  );
}
