'use client';

import { Info } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ErrorState } from '@/components/error-state';
import { EmptyState } from '@/components/empty-state';
import { DataFreshness } from '@/components/data-freshness';
import { ImbalanceMeter } from '@/components/imbalance-meter';
import { LiquidityHeatmap } from '@/components/liquidity-heatmap';
import { usePolling } from '@/lib/use-polling';
import type { LiquidityReport, LiquidityZone } from '@/lib/api';
import { formatUSD } from '@/lib/format';
import { cn } from '@/lib/utils';

function isEstimated(zone: LiquidityZone): boolean {
  return zone.type.startsWith('estimated_');
}

function ZoneTypeBadge({ zone }: { zone: LiquidityZone }) {
  if (isEstimated(zone)) {
    return <Badge variant="warning">ESTIMATE</Badge>;
  }
  return <Badge variant="info">observed</Badge>;
}

function WallList({ title, walls, side }: { title: string; walls: { price: number; size_usd: number; exchange: string }[]; side: 'bid' | 'ask' }) {
  const sorted = [...walls].sort((a, b) => b.size_usd - a.size_usd).slice(0, 10);
  const max = sorted.length > 0 ? Math.max(...sorted.map((w) => w.size_usd)) : 0;
  return (
    <Card>
      <CardHeader><CardTitle>{title}</CardTitle></CardHeader>
      <CardContent>
        {sorted.length === 0 ? (
          <EmptyState title="No walls detected" className="p-4" />
        ) : (
          <div className="space-y-1">
            {sorted.map((w, i) => (
              <div key={i} className="relative flex items-center justify-between overflow-hidden rounded px-2 py-1 text-xs">
                <div
                  className={cn('absolute inset-y-0', side === 'bid' ? 'left-0 bg-emerald-500/10' : 'right-0 bg-rose-500/10')}
                  style={{ width: `${max > 0 ? (w.size_usd / max) * 100 : 0}%` }}
                />
                <span className="relative tabular font-medium text-zinc-200">{formatUSD(w.price)}</span>
                <span className="relative tabular text-zinc-400">{formatUSD(w.size_usd)}</span>
                <span className="relative text-[10px] capitalize text-zinc-500">{w.exchange}</span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function LiquidityTab({ symbol }: { symbol: string }) {
  const { data, error, loading, refresh } = usePolling<LiquidityReport>(
    `/coins/${encodeURIComponent(symbol)}/liquidity`,
    10000,
  );

  if (loading && !data) return <Skeleton className="h-96 w-full" />;
  if (error && !data) return <ErrorState error={error} onRetry={refresh} />;
  if (!data) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-end gap-3">
        {data.mid_price != null && (
          <span className="text-xs text-zinc-500">
            mid <span className="tabular font-medium text-zinc-200">{formatUSD(data.mid_price)}</span>
          </span>
        )}
        <DataFreshness updatedAt={data.updated_at} stale={data.stale} />
      </div>

      <Card>
        <CardHeader><CardTitle>Book imbalance</CardTitle></CardHeader>
        <CardContent>
          <ImbalanceMeter value={data.imbalance} leftLabel="ask heavy" rightLabel="bid heavy" />
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <WallList title="Bid walls" walls={data.walls.bids} side="bid" />
        <WallList title="Ask walls" walls={data.walls.asks} side="ask" />
      </div>

      <Card>
        <CardHeader><CardTitle>Liquidity zones</CardTitle></CardHeader>
        <CardContent>
          {data.zones.length === 0 ? (
            <EmptyState title="No zones detected" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Zone</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Price range</TableHead>
                  <TableHead>Strength</TableHead>
                  <TableHead className="text-right">Size</TableHead>
                  <TableHead>Exchange</TableHead>
                  <TableHead>Source</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.zones.map((z, i) => (
                  <TableRow key={i}>
                    <TableCell className="whitespace-normal text-xs text-zinc-300">{z.label}</TableCell>
                    <TableCell><ZoneTypeBadge zone={z} /></TableCell>
                    <TableCell className="text-xs">
                      {formatUSD(z.price_low)} — {formatUSD(z.price_high)}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-16 overflow-hidden rounded-full bg-zinc-800">
                          <div className="h-full bg-amber-500" style={{ width: `${Math.min(100, z.strength * 100)}%` }} />
                        </div>
                        <span className="text-[10px] text-zinc-500 tabular">{z.strength.toFixed(2)}</span>
                      </div>
                    </TableCell>
                    <TableCell className="text-right">{z.size_usd != null ? formatUSD(z.size_usd) : '—'}</TableCell>
                    <TableCell className="capitalize text-zinc-400">{z.exchange ?? 'aggregated'}</TableCell>
                    <TableCell className="text-[11px] text-zinc-500">{z.source}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Liquidity heatmap</CardTitle></CardHeader>
        <CardContent>
          {!data.heatmap || data.heatmap.price_points.length === 0 || data.heatmap.time_points.length === 0 ? (
            <EmptyState title="No heatmap data" description="The source did not return a liquidity heatmap for this asset." />
          ) : (
            <LiquidityHeatmap
              pricePoints={data.heatmap.price_points}
              timePoints={data.heatmap.time_points}
              intensity={data.heatmap.intensity}
            />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Info className="h-4 w-4 text-zinc-500" /> Observed vs estimated</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-[11px] leading-relaxed text-zinc-500">{data.disclaimer}</p>
        </CardContent>
      </Card>
    </div>
  );
}
