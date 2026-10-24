'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { ErrorState } from '@/components/error-state';
import { EmptyState } from '@/components/empty-state';
import { DataFreshness } from '@/components/data-freshness';
import { StatCard } from '@/components/stat-card';
import { usePolling } from '@/lib/use-polling';
import type { ChartResponse, Timeframe } from '@/lib/api';
import { bollinger, emaSeries, lastValue, macdSeries, rsiSeries, smaSeries } from '@/lib/indicators';
import { formatUSD } from '@/lib/format';
import { cn } from '@/lib/utils';

const TF_OPTIONS: Timeframe[] = ['1h', '4h', '1d'];

function rsiLabel(v: number | null): string {
  if (v == null) return 'n/a';
  if (v >= 70) return 'overbought';
  if (v <= 30) return 'oversold';
  return 'neutral';
}

export function IndicatorsTab({ symbol }: { symbol: string }) {
  const [timeframe, setTimeframe] = useState<Timeframe>('1h');
  const { data, error, loading, refresh } = usePolling<ChartResponse>(
    `/coins/${encodeURIComponent(symbol)}/chart?timeframe=${timeframe}&source=auto`,
    60000,
  );

  const closes = data?.candles.map((c) => c.close) ?? [];
  const lastClose = closes.length > 0 ? closes[closes.length - 1] : null;

  const sma20 = lastValue(smaSeries(closes, 20));
  const sma50 = lastValue(smaSeries(closes, 50));
  const ema12 = lastValue(emaSeries(closes, 12));
  const ema26 = lastValue(emaSeries(closes, 26));
  const rsi14 = lastValue(rsiSeries(closes, 14));
  const macd = macdSeries(closes);
  const macdLine = lastValue(macd.macd);
  const macdSignal = lastValue(macd.signal);
  const macdHist = lastValue(macd.histogram);
  const bb = bollinger(closes, 20, 2);

  const aboveBelow = (ref: number | null) =>
    ref == null || lastClose == null ? undefined : lastClose >= ref ? 'price above' : 'price below';

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="inline-flex h-8 items-center gap-1 rounded-lg border border-zinc-800 bg-panel-2 p-1">
          {TF_OPTIONS.map((tf) => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={cn(
                'rounded-md px-2.5 py-1 text-xs font-medium transition-colors',
                timeframe === tf ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-400 hover:text-zinc-200',
              )}
            >
              {tf}
            </button>
          ))}
        </div>
        {data && (
          <span className="text-[11px] text-zinc-500">
            Computed client-side from {data.source} candles ({timeframe})
          </span>
        )}
        {data && <DataFreshness updatedAt={data.updated_at} stale={data.stale} className="ml-auto" />}
      </div>

      {loading && !data ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 8 }, (_, i) => <Skeleton key={i} className="h-24 w-full" />)}
        </div>
      ) : error && !data ? (
        <ErrorState error={error} onRetry={refresh} />
      ) : !data || data.candles.length < 50 ? (
        <EmptyState title="Not enough candles" description="At least 50 candles are required to compute all indicators." />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          <StatCard title="SMA 20" value={formatUSD(sma20)} footer={aboveBelow(sma20)} />
          <StatCard title="SMA 50" value={formatUSD(sma50)} footer={aboveBelow(sma50)} />
          <StatCard title="EMA 12" value={formatUSD(ema12)} footer={aboveBelow(ema12)} />
          <StatCard title="EMA 26" value={formatUSD(ema26)} footer={aboveBelow(ema26)} />
          <StatCard
            title="RSI 14"
            value={rsi14 == null ? '—' : rsi14.toFixed(1)}
            footer={rsiLabel(rsi14)}
            className={cn(rsi14 != null && rsi14 >= 70 && 'border-rose-500/40', rsi14 != null && rsi14 <= 30 && 'border-emerald-500/40')}
          />
          <StatCard
            title="MACD (12,26,9)"
            value={macdLine == null ? '—' : macdLine.toFixed(2)}
            footer={
              macdSignal != null && macdHist != null
                ? `signal ${macdSignal.toFixed(2)} · hist ${macdHist >= 0 ? '+' : ''}${macdHist.toFixed(2)}`
                : undefined
            }
          />
          <StatCard
            title="Bollinger (20,2)"
            value={bb.middle == null ? '—' : formatUSD(bb.middle)}
            footer={bb.upper != null && bb.lower != null ? `${formatUSD(bb.lower)} — ${formatUSD(bb.upper)}` : undefined}
          />
          <StatCard
            title="%B"
            value={bb.percentB == null ? '—' : bb.percentB.toFixed(2)}
            footer={bb.percentB != null ? (bb.percentB > 1 ? 'above upper band' : bb.percentB < 0 ? 'below lower band' : 'inside bands') : undefined}
          />
        </div>
      )}

      <Card>
        <CardHeader><CardTitle>Note</CardTitle></CardHeader>
        <CardContent>
          <p className="text-[11px] leading-relaxed text-zinc-500">
            These indicators are computed client-side from {data ? `${data.source} ` : ''}candles returned by the
            chart endpoint ({timeframe}). They are for informational purposes only.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
