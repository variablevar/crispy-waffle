'use client';

import { Info } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tooltip } from '@/components/ui/tooltip';
import { ErrorState } from '@/components/error-state';
import { EmptyState } from '@/components/empty-state';
import { DataFreshness } from '@/components/data-freshness';
import { ImbalanceMeter } from '@/components/imbalance-meter';
import { MiniLineChart } from '@/components/mini-line-chart';
import { usePolling } from '@/lib/use-polling';
import type { PressureReport } from '@/lib/api';
import { formatUSD } from '@/lib/format';
import { cn } from '@/lib/utils';

const CONFIDENCE_VARIANT = { high: 'success', medium: 'warning', low: 'destructive' } as const;
const TF_ORDER = ['15m', '1h', '4h', '1d', '1w'];

function TakerBars({ buy, sell }: { buy: number | null; sell: number | null }) {
  if (buy == null || sell == null || buy + sell <= 0) {
    return <p className="text-xs text-zinc-500">Taker flow unavailable.</p>;
  }
  const total = buy + sell;
  const buyPct = (buy / total) * 100;
  return (
    <div className="space-y-1.5">
      <div className="flex h-4 w-full overflow-hidden rounded-full">
        <div className="bg-emerald-500/80" style={{ width: `${buyPct}%` }} />
        <div className="bg-rose-500/80" style={{ width: `${100 - buyPct}%` }} />
      </div>
      <div className="flex justify-between text-[11px] tabular">
        <span className="text-emerald-400">buy {formatUSD(buy)}</span>
        <span className="text-rose-400">sell {formatUSD(sell)}</span>
      </div>
    </div>
  );
}

function RatioBar({ label, ratio }: { label: string; ratio: number | null }) {
  // ratio buy/sell: 1 = balanced. Map to 0..100 fill where 50% = ratio 1.
  const pct = ratio == null || ratio < 0 ? null : (ratio / (ratio + 1)) * 100;
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-[11px]">
        <span className="text-zinc-400">{label}</span>
        <span className="tabular text-zinc-300">{ratio == null ? '—' : ratio.toFixed(2)}</span>
      </div>
      <div className="relative h-1.5 overflow-hidden rounded-full bg-zinc-800">
        <div className="absolute left-1/2 top-0 h-full w-px bg-zinc-600" />
        {pct != null && (
          <div className={cn('absolute top-0 h-full', pct >= 50 ? 'bg-emerald-500' : 'bg-rose-500')}
            style={{ left: pct >= 50 ? '50%' : `${pct}%`, width: `${Math.abs(pct - 50)}%` }} />
        )}
      </div>
    </div>
  );
}

export function PressureTab({ symbol }: { symbol: string }) {
  const { data, error, loading, refresh } = usePolling<PressureReport>(
    `/coins/${encodeURIComponent(symbol)}/pressure`,
    10000,
  );

  if (loading && !data) return <Skeleton className="h-96 w-full" />;
  if (error && !data) return <ErrorState error={error} onRetry={refresh} />;
  if (!data) return null;

  const tfEntries = TF_ORDER.filter((tf) => tf in data.timeframes).map((tf) => [tf, data.timeframes[tf]] as const);
  const cvdColor = data.cvd.length > 1 && data.cvd[data.cvd.length - 1].value >= data.cvd[0].value ? '#10b981' : '#f43f5e';

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-end gap-2">
        <Tooltip content={data.methodology}>
          <Badge variant={CONFIDENCE_VARIANT[data.confidence]} className="cursor-help">
            <Info className="h-3 w-3" /> confidence: {data.confidence}
          </Badge>
        </Tooltip>
        <DataFreshness updatedAt={data.updated_at} stale={data.stale} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Taker buy / sell volume</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <TakerBars buy={data.taker_buy_volume} sell={data.taker_sell_volume} />
            <RatioBar label="Taker ratio (buy/sell)" ratio={data.taker_ratio} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Book imbalance (top-of-book, depth weighted)</CardTitle></CardHeader>
          <CardContent>
            <ImbalanceMeter value={data.book_imbalance} leftLabel="ask heavy" rightLabel="bid heavy" />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle>CVD (cumulative volume delta)</CardTitle></CardHeader>
        <CardContent>
          {data.cvd.length < 2 ? (
            <EmptyState title="No CVD data" className="p-4" />
          ) : (
            <MiniLineChart series={[{ name: 'CVD', color: cvdColor, data: data.cvd }]} height={200} />
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Spot vs futures taker ratio</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <RatioBar label="Spot ratio" ratio={data.spot_vs_futures.spot_ratio} />
            <RatioBar label="Futures ratio" ratio={data.spot_vs_futures.futures_ratio} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Per-timeframe breakdown</CardTitle></CardHeader>
          <CardContent>
            {tfEntries.length === 0 ? (
              <EmptyState title="No timeframe data" className="p-4" />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>TF</TableHead>
                    <TableHead className="text-right">Buy</TableHead>
                    <TableHead className="text-right">Sell</TableHead>
                    <TableHead className="text-right">Ratio</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {tfEntries.map(([tf, v]) => (
                    <TableRow key={tf}>
                      <TableCell className="font-medium text-zinc-200">{tf}</TableCell>
                      <TableCell className="text-right text-emerald-400">{formatUSD(v.buy)}</TableCell>
                      <TableCell className="text-right text-rose-400">{formatUSD(v.sell)}</TableCell>
                      <TableCell className="text-right">{v.ratio == null ? '—' : v.ratio.toFixed(2)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Info className="h-4 w-4 text-zinc-500" /> Methodology</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-[11px] leading-relaxed text-zinc-500">{data.methodology}</p>
        </CardContent>
      </Card>
    </div>
  );
}
