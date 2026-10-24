'use client';

import { Gauge } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { ErrorState } from '@/components/error-state';
import { DataFreshness } from '@/components/data-freshness';
import { Sparkline } from '@/components/sparkline';
import { usePolling } from '@/lib/use-polling';
import type { FearGreed } from '@/lib/api';

function gaugeColor(value: number): string {
  if (value < 25) return '#f43f5e'; // extreme fear
  if (value < 45) return '#fb923c';
  if (value < 55) return '#f59e0b';
  if (value < 75) return '#a3e635';
  return '#10b981'; // extreme greed
}

function polar(cx: number, cy: number, r: number, angleDeg: number) {
  const rad = ((angleDeg - 180) * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function arcPath(cx: number, cy: number, r: number, a0: number, a1: number) {
  const p0 = polar(cx, cy, r, a0);
  const p1 = polar(cx, cy, r, a1);
  const large = a1 - a0 > 180 ? 1 : 0;
  return `M ${p0.x} ${p0.y} A ${r} ${r} 0 ${large} 1 ${p1.x} ${p1.y}`;
}

export function FearGreedGauge() {
  const { data, error, loading, refresh } = usePolling<FearGreed>('/market/fear-greed', 60000);

  if (loading && !data) {
    return (
      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2"><Gauge className="h-4 w-4 text-zinc-500" /> Fear &amp; Greed</CardTitle></CardHeader>
        <CardContent><Skeleton className="h-36 w-full" /></CardContent>
      </Card>
    );
  }
  if (error && !data) {
    return (
      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2"><Gauge className="h-4 w-4 text-zinc-500" /> Fear &amp; Greed</CardTitle></CardHeader>
        <CardContent><ErrorState error={error} onRetry={refresh} compact /></CardContent>
      </Card>
    );
  }
  if (!data) return null;

  const value = Math.max(0, Math.min(100, data.value));
  const cx = 100;
  const cy = 100;
  const r = 80;
  const angle = (value / 100) * 180;
  const needleTip = polar(cx, cy, r - 18, angle);
  const historyValues = (data.history ?? []).map((h) => h.value);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="flex items-center gap-2">
          <Gauge className="h-4 w-4 text-zinc-500" /> Fear &amp; Greed
        </CardTitle>
        <DataFreshness updatedAt={data.updated_at} stale={data.stale} />
      </CardHeader>
      <CardContent>
        <div className="flex items-center gap-4">
          <svg viewBox="0 0 200 112" className="w-44 shrink-0">
            <path d={arcPath(cx, cy, r, 0, 180)} fill="none" stroke="#27272a" strokeWidth={14} strokeLinecap="round" />
            <path
              d={arcPath(cx, cy, r, 0, Math.max(0.5, angle))}
              fill="none"
              stroke={gaugeColor(value)}
              strokeWidth={14}
              strokeLinecap="round"
            />
            <line x1={cx} y1={cy} x2={needleTip.x} y2={needleTip.y} stroke="#f4f4f5" strokeWidth={2.5} strokeLinecap="round" />
            <circle cx={cx} cy={cy} r={5} fill="#f4f4f5" />
            <text x={cx} y={cy - 34} textAnchor="middle" className="fill-zinc-100" fontSize={26} fontWeight={700}>
              {value}
            </text>
            <text x={4} y={110} fontSize={8} className="fill-zinc-500">Fear</text>
            <text x={196} y={110} textAnchor="end" fontSize={8} className="fill-zinc-500">Greed</text>
          </svg>
          <div className="min-w-0 flex-1 space-y-2">
            <div className="text-sm font-semibold" style={{ color: gaugeColor(value) }}>
              {data.classification}
            </div>
            {historyValues.length > 1 && (
              <div>
                <div className="mb-1 text-[10px] uppercase tracking-wider text-zinc-500">history</div>
                <Sparkline data={historyValues} width={140} height={32} />
              </div>
            )}
            <div className="text-[10px] text-zinc-600">{data.attribution || `Source: ${data.source}`}</div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
