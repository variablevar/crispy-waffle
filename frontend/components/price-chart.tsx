'use client';

import { useEffect, useRef, useState } from 'react';
import {
  createChart,
  ColorType,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from 'lightweight-charts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { ErrorState } from '@/components/error-state';
import { EmptyState } from '@/components/empty-state';
import { DataFreshness } from '@/components/data-freshness';
import { usePolling } from '@/lib/use-polling';
import type { ChartResponse, Timeframe } from '@/lib/api';
import { cn } from '@/lib/utils';

const TIMEFRAMES: Timeframe[] = ['15m', '1h', '4h', '1d', '1w'];

const POLL_MS: Record<Timeframe, number> = {
  '15m': 15000,
  '1h': 30000,
  '4h': 60000,
  '1d': 60000,
  '1w': 60000,
};

export function PriceChart({ symbol }: { symbol: string }) {
  const [timeframe, setTimeframe] = useState<Timeframe>('1h');
  const { data, error, loading, refresh } = usePolling<ChartResponse>(
    `/coins/${encodeURIComponent(symbol)}/chart?timeframe=${timeframe}&source=auto`,
    POLL_MS[timeframe],
  );

  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);

  // create chart once
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const chart = createChart(el, {
      layout: {
        background: { type: ColorType.Solid, color: '#0a0b0f' },
        textColor: '#71717a',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: '#1c1d24' },
        horzLines: { color: '#1c1d24' },
      },
      rightPriceScale: { borderColor: '#27272a' },
      timeScale: { borderColor: '#27272a', timeVisible: true, secondsVisible: false },
      crosshair: {
        vertLine: { color: '#3f3f46' },
        horzLine: { color: '#3f3f46' },
      },
      width: el.clientWidth,
      height: 380,
    });
    const candles = chart.addCandlestickSeries({
      upColor: '#10b981',
      downColor: '#f43f5e',
      borderVisible: false,
      wickUpColor: '#10b981',
      wickDownColor: '#f43f5e',
    });
    const volume = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: '',
    });
    chart.priceScale('').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });

    chartRef.current = chart;
    candleSeriesRef.current = candles;
    volumeSeriesRef.current = volume;

    const observer = new ResizeObserver(() => {
      chart.applyOptions({ width: el.clientWidth });
    });
    observer.observe(el);

    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, []);

  // push data
  useEffect(() => {
    if (!data || !candleSeriesRef.current || !volumeSeriesRef.current) return;
    const candles = data.candles.map((c) => ({
      time: c.time as UTCTimestamp,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));
    candleSeriesRef.current.setData(candles);
    volumeSeriesRef.current.setData(
      data.candles.map((c) => ({
        time: c.time as UTCTimestamp,
        value: c.volume,
        color: c.close >= c.open ? 'rgba(16,185,129,0.35)' : 'rgba(244,63,94,0.35)',
      })),
    );
    chartRef.current?.timeScale().fitContent();
  }, [data]);

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2 space-y-0">
        <CardTitle className="flex items-center gap-3">
          Price chart
          {data && <span className="text-[11px] font-normal text-zinc-500">Source: {data.source}</span>}
        </CardTitle>
        <div className="flex items-center gap-3">
          {data && <DataFreshness updatedAt={data.updated_at} stale={data.stale} />}
          <div className="inline-flex h-8 items-center gap-1 rounded-lg border border-zinc-800 bg-panel-2 p-1">
            {TIMEFRAMES.map((tf) => (
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
        </div>
      </CardHeader>
      <CardContent>
        {loading && !data ? (
          <Skeleton className="h-[380px] w-full" />
        ) : error && !data ? (
          <ErrorState error={error} onRetry={refresh} />
        ) : !data || data.candles.length === 0 ? (
          <EmptyState title="No candles" description="The source returned no candles for this timeframe." />
        ) : (
          <>
            {error && <ErrorState error={error} onRetry={refresh} compact className="mb-2" />}
            <div ref={containerRef} className="w-full" />
          </>
        )}
      </CardContent>
    </Card>
  );
}
