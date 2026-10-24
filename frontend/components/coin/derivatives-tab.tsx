'use client';

import { Info } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { StatCard } from '@/components/stat-card';
import { ErrorState } from '@/components/error-state';
import { EmptyState } from '@/components/empty-state';
import { UnavailableState } from '@/components/unavailable-state';
import { DataFreshness } from '@/components/data-freshness';
import { MiniLineChart } from '@/components/mini-line-chart';
import { usePolling } from '@/lib/use-polling';
import type { DerivativesReport } from '@/lib/api';
import { formatFunding, formatNumber, formatUSD, unixTimeAgo } from '@/lib/format';
import { cn } from '@/lib/utils';

export function DerivativesTab({ symbol }: { symbol: string }) {
  const { data, error, loading, refresh } = usePolling<DerivativesReport>(
    `/coins/${encodeURIComponent(symbol)}/derivatives`,
    15000,
  );

  if (loading && !data) return <Skeleton className="h-96 w-full" />;
  if (error && !data) return <ErrorState error={error} onRetry={refresh} />;
  if (!data) return null;

  const binanceFundingHistory = data.funding.history
    .filter((h) => h.exchange === 'binance')
    .map((h) => ({ time: h.time, value: h.value * 100 }));
  const bybitFundingHistory = data.funding.history
    .filter((h) => h.exchange === 'bybit')
    .map((h) => ({ time: h.time, value: h.value * 100 }));

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <DataFreshness updatedAt={data.updated_at} stale={data.stale} />
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard title="Funding · Binance" value={formatFunding(data.funding.binance)} />
        <StatCard title="Funding · Bybit" value={formatFunding(data.funding.bybit)} />
        <StatCard title="OI · Binance" value={data.open_interest.binance != null ? formatNumber(data.open_interest.binance, 4) : '—'} footer={`in ${symbol}`} />
        <StatCard title="Basis (perp − spot)" value={data.basis != null ? `${data.basis >= 0 ? '+' : ''}${formatUSD(data.basis)}` : '—'} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Funding rate history (%)</CardTitle></CardHeader>
          <CardContent>
            {binanceFundingHistory.length < 2 && bybitFundingHistory.length < 2 ? (
              <EmptyState title="No funding history" className="p-4" />
            ) : (
              <MiniLineChart
                series={[
                  { name: 'binance', color: '#f59e0b', data: binanceFundingHistory },
                  { name: 'bybit', color: '#38bdf8', data: bybitFundingHistory },
                ].filter((s) => s.data.length > 0)}
                height={200}
              />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Open interest history</CardTitle></CardHeader>
          <CardContent>
            {data.open_interest.history.length < 2 ? (
              <EmptyState title="No OI history" className="p-4" />
            ) : (
              <MiniLineChart
                series={[{ name: `OI (${symbol})`, color: '#a78bfa', data: data.open_interest.history }]}
                height={200}
              />
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Long / short ratio</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {!data.long_short_ratio ? (
              <EmptyState title="No long/short data" className="p-4" />
            ) : (
              (['binance', 'bybit'] as const).map((ex) => {
                const r = data.long_short_ratio?.[ex] ?? null;
                const pct = r == null || r < 0 ? null : (r / (r + 1)) * 100;
                return (
                  <div key={ex} className="space-y-1">
                    <div className="flex justify-between text-[11px]">
                      <span className="capitalize text-zinc-400">{ex}</span>
                      <span className="tabular text-zinc-300">{r == null ? '—' : r.toFixed(2)}</span>
                    </div>
                    <div className="flex h-2 w-full overflow-hidden rounded-full bg-zinc-800">
                      {pct != null && <div className="bg-emerald-500" style={{ width: `${pct}%` }} />}
                      {pct != null && <div className="bg-rose-500" style={{ width: `${100 - pct}%` }} />}
                    </div>
                    <div className="flex justify-between text-[10px] text-zinc-600">
                      <span>long</span><span>short</span>
                    </div>
                  </div>
                );
              })
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle>Liquidations</CardTitle>
            <span className="text-[11px] text-zinc-500">source: {data.liquidations.source || '—'}</span>
          </CardHeader>
          <CardContent className="space-y-3">
            {!data.liquidations.available ? (
              <>
                <UnavailableState reason="Liquidation data is not available from the configured sources." />
                {data.liquidations.note && (
                  <p className="rounded-md border border-zinc-800 bg-panel-2/60 p-3 text-[11px] leading-relaxed text-zinc-500">
                    <Info className="mr-1 inline h-3 w-3" /> {data.liquidations.note}
                  </p>
                )}
              </>
            ) : (
              <>
                {data.liquidations.recent.length === 0 ? (
                  <EmptyState title="No recent liquidations" className="p-4" />
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Time</TableHead>
                        <TableHead>Side</TableHead>
                        <TableHead className="text-right">Size</TableHead>
                        <TableHead>Exchange</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.liquidations.recent.map((liq, i) => (
                        <TableRow key={i}>
                          <TableCell className="text-zinc-500">{unixTimeAgo(liq.time)}</TableCell>
                          <TableCell className={cn('font-medium', liq.side === 'long' ? 'text-rose-400' : 'text-emerald-400')}>
                            {liq.side}
                          </TableCell>
                          <TableCell className="text-right">{formatUSD(liq.size_usd)}</TableCell>
                          <TableCell className="capitalize text-zinc-400">{liq.exchange}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
                {data.liquidations.note && (
                  <p className="rounded-md border border-zinc-800 bg-panel-2/60 p-3 text-[11px] leading-relaxed text-zinc-500">
                    <Info className="mr-1 inline h-3 w-3" /> {data.liquidations.note}
                  </p>
                )}
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
