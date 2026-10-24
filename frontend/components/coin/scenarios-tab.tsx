'use client';

import { useState } from 'react';
import { AlertTriangle, Check, ChevronDown, ChevronRight, Info, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tooltip } from '@/components/ui/tooltip';
import { ErrorState } from '@/components/error-state';
import { EmptyState } from '@/components/empty-state';
import { usePolling } from '@/lib/use-polling';
import type { Scenario, ScenariosResponse } from '@/lib/api';
import { formatUSD, timeAgo } from '@/lib/format';
import { cn } from '@/lib/utils';

function BiasBadge({ bias }: { bias: Scenario['bias'] }) {
  if (bias === 'long') return <Badge variant="success">LONG</Badge>;
  if (bias === 'short') return <Badge variant="destructive">SHORT</Badge>;
  return <Badge variant="default">NO-TRADE</Badge>;
}

function Collapsible({ title, count, children, defaultOpen = false }: { title: string; count?: number; children: React.ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-md border border-zinc-800/80">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-medium text-zinc-300 hover:bg-zinc-800/40"
      >
        {open ? <ChevronDown className="h-3.5 w-3.5 text-zinc-500" /> : <ChevronRight className="h-3.5 w-3.5 text-zinc-500" />}
        {title}
        {count != null && <span className="text-zinc-600">({count})</span>}
      </button>
      {open && <div className="border-t border-zinc-800/80 px-3 py-2">{children}</div>}
    </div>
  );
}

function StringList({ items }: { items: string[] }) {
  if (items.length === 0) return <p className="text-[11px] text-zinc-600">none</p>;
  return (
    <ul className="list-disc space-y-1 pl-4 text-[11px] leading-relaxed text-zinc-400">
      {items.map((s, i) => <li key={i}>{s}</li>)}
    </ul>
  );
}

function ConfidenceMeter({ value, methodology }: { value: number; methodology: string }) {
  const pct = Math.round(value * 100);
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-[11px]">
        <Tooltip content={methodology}>
          <span className="inline-flex cursor-help items-center gap-1 text-zinc-400">
            <Info className="h-3 w-3" /> confidence
          </span>
        </Tooltip>
        <span className="tabular text-zinc-300">{pct}%</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-800">
        <div
          className={cn('h-full', pct >= 66 ? 'bg-emerald-500' : pct >= 33 ? 'bg-amber-500' : 'bg-rose-500')}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function ScenarioCard({ scenario }: { scenario: Scenario }) {
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-2 space-y-0">
        <CardTitle className="flex items-center gap-2">
          <BiasBadge bias={scenario.bias} />
          <span>{scenario.title}</span>
        </CardTitle>
        <span className="flex items-center gap-2 text-[10px] text-zinc-500 tabular">
          {scenario.stale && <Badge variant="warning">STALE</Badge>}
          generated {timeAgo(scenario.generated_at)}
        </span>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">{scenario.type.replace(/_/g, ' ')}</Badge>
          <Badge variant="outline">{scenario.asset}</Badge>
        </div>

        <ConfidenceMeter value={scenario.confidence} methodology={scenario.methodology} />

        <div className="grid gap-2 md:grid-cols-3">
          <Collapsible title="Trigger conditions" count={scenario.trigger_conditions.length}>
            <StringList items={scenario.trigger_conditions} />
          </Collapsible>
          <Collapsible title="Confirmation signals" count={scenario.confirmation_signals.length}>
            <StringList items={scenario.confirmation_signals} />
          </Collapsible>
          <Collapsible title="Invalidation" count={scenario.invalidation_conditions.length}>
            <StringList items={scenario.invalidation_conditions} />
          </Collapsible>
        </div>

        {scenario.target_zones.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {scenario.target_zones.map((z, i) => (
              <Badge key={i} variant="info" className="tabular">
                {z.label}: {formatUSD(z.price_low)} — {formatUSD(z.price_high)}
              </Badge>
            ))}
          </div>
        )}

        {scenario.evidence.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Indicator</TableHead>
                <TableHead>Value</TableHead>
                <TableHead className="w-20">Supports</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {scenario.evidence.map((e, i) => (
                <TableRow key={i}>
                  <TableCell className="text-zinc-300">{e.indicator}</TableCell>
                  <TableCell className="text-zinc-400">{e.value}</TableCell>
                  <TableCell>
                    {e.supports ? <Check className="h-4 w-4 text-emerald-400" /> : <X className="h-4 w-4 text-rose-400" />}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        <Collapsible title="Risks" count={scenario.risks.length}>
          <StringList items={scenario.risks} />
        </Collapsible>

        <Collapsible title="Methodology">
          <p className="text-[11px] leading-relaxed text-zinc-500">{scenario.methodology}</p>
        </Collapsible>
      </CardContent>
    </Card>
  );
}

export function ScenariosTab({ symbol }: { symbol: string }) {
  const { data, error, loading, refresh } = usePolling<ScenariosResponse>(
    `/coins/${encodeURIComponent(symbol)}/scenarios`,
    60000,
  );

  if (loading && !data) return <Skeleton className="h-96 w-full" />;
  if (error && !data) return <ErrorState error={error} onRetry={refresh} />;
  if (!data) return null;

  const marketStateEntries = Object.entries(data.market_state ?? {});

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
        <p className="text-xs text-amber-300">Rule-based educational analysis — not financial advice.</p>
      </div>

      {marketStateEntries.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {marketStateEntries.map(([k, v]) => (
            <Badge key={k} variant="outline" className="tabular">
              {k.replace(/_/g, ' ')}: <span className="ml-1 text-zinc-200">{v}</span>
            </Badge>
          ))}
        </div>
      )}

      {data.scenarios.length === 0 ? (
        <EmptyState title="No scenarios" description="The engine produced no scenarios for the current market state." />
      ) : (
        data.scenarios.map((s) => <ScenarioCard key={s.id} scenario={s} />)
      )}
    </div>
  );
}
