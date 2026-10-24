'use client';

import { useEffect, useRef } from 'react';
import {
  createChart,
  ColorType,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from 'lightweight-charts';
import { cn } from '@/lib/utils';

export interface LineSeriesData {
  time: number; // unix seconds
  value: number;
}

interface MiniLineChartProps {
  series: { name: string; color: string; data: LineSeriesData[] }[];
  height?: number;
  className?: string;
}

/** Small lightweight-charts line chart for CVD / funding / OI histories. */
export function MiniLineChart({ series, height = 180, className }: MiniLineChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRefs = useRef<ISeriesApi<'Line'>[]>([]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const chart = createChart(el, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#71717a',
        fontSize: 10,
      },
      grid: {
        vertLines: { color: '#1c1d24' },
        horzLines: { color: '#1c1d24' },
      },
      rightPriceScale: { borderColor: '#27272a' },
      timeScale: { borderColor: '#27272a', timeVisible: true, secondsVisible: false },
      width: el.clientWidth,
      height,
    });
    chartRef.current = chart;
    seriesRefs.current = series.map((s) =>
      chart.addLineSeries({ color: s.color, lineWidth: 2, priceLineVisible: false }),
    );
    const observer = new ResizeObserver(() => chart.applyOptions({ width: el.clientWidth }));
    observer.observe(el);
    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRefs.current = [];
    };
    // recreate chart when series definitions (names/colors/count) change
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [series.map((s) => `${s.name}:${s.color}`).join('|'), height]);

  useEffect(() => {
    series.forEach((s, i) => {
      const ref = seriesRefs.current[i];
      if (!ref) return;
      ref.setData(s.data.map((d) => ({ time: d.time as UTCTimestamp, value: d.value })));
    });
    chartRef.current?.timeScale().fitContent();
  }, [series]);

  return (
    <div className={cn('w-full', className)}>
      <div className="mb-1 flex flex-wrap gap-3">
        {series.map((s) => (
          <span key={s.name} className="inline-flex items-center gap-1.5 text-[11px] text-zinc-400">
            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: s.color }} />
            {s.name}
          </span>
        ))}
      </div>
      <div ref={containerRef} className="w-full" />
    </div>
  );
}
