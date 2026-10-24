'use client';

import { useState } from 'react';
import {
  Activity,
  ArrowLeftRight,
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  Crosshair,
  Droplets,
  Newspaper,
  Percent,
  RefreshCcw,
  Sparkles,
  Wifi,
  WifiOff,
  X,
  XCircle,
  Zap,
  type LucideIcon,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Tooltip } from '@/components/ui/tooltip';
import type { AgentEvent, AgentEventSeverity, AgentEventType } from '@/lib/agent-api';
import { timeAgo } from '@/lib/format';
import { cn } from '@/lib/utils';

const TYPE_ICON: Record<AgentEventType, LucideIcon> = {
  PRICE_LEVEL_CROSSED: Crosshair,
  LIQUIDITY_ZONE_APPROACH: Droplets,
  LIQUIDITY_ZONE_BREACHED: Droplets,
  LIQUIDITY_SWEEP_DETECTED: Droplets,
  CVD_DIVERGENCE: Activity,
  OPEN_INTEREST_SPIKE: Activity,
  FUNDING_EXTREME: Percent,
  LONG_LIQUIDATION_BURST: Zap,
  SHORT_LIQUIDATION_BURST: Zap,
  CROSS_EXCHANGE_DIVERGENCE: ArrowLeftRight,
  NEWS_BREAKING: Newspaper,
  MARKET_REGIME_CHANGED: RefreshCcw,
  SCENARIO_CREATED: Sparkles,
  SCENARIO_INVALIDATED: XCircle,
  DATA_STALE: WifiOff,
  DATA_RECOVERED: Wifi,
};

const SEVERITY_STYLE: Record<AgentEventSeverity, { badge: 'default' | 'warning' | 'destructive'; border: string; icon: string }> = {
  info: { badge: 'default', border: 'border-l-zinc-600', icon: 'text-zinc-400' },
  warning: { badge: 'warning', border: 'border-l-amber-500', icon: 'text-amber-400' },
  critical: { badge: 'destructive', border: 'border-l-rose-500', icon: 'text-rose-400' },
};

function MeasurementsBlock({ label, estimated, data }: { label: string; estimated?: boolean; data: Record<string, unknown> | undefined }) {
  if (!data || Object.keys(data).length === 0) return null;
  return (
    <div>
      <p className={cn('mb-1 text-[10px] font-semibold uppercase tracking-wide', estimated ? 'text-amber-400' : 'text-zinc-500')}>
        {estimated ? 'ESTIMATED' : label}
      </p>
      <pre className="overflow-x-auto rounded border border-zinc-800 bg-zinc-900/80 p-2 text-[10px] leading-relaxed text-zinc-300 tabular">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  );
}

function ConfidenceMeter({ value }: { value: number }) {
  const pct = Math.round(Math.min(Math.max(value, 0), 1) * 100);
  const bar = pct >= 66 ? 'bg-emerald-500' : pct >= 33 ? 'bg-amber-500' : 'bg-rose-500';
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-[10px] uppercase tracking-wide">
        <span className="font-semibold text-zinc-500">Confidence</span>
        <span className="text-zinc-400 tabular">{pct}%</span>
      </div>
      <div className="h-1.5 w-full rounded bg-zinc-800">
        <div className={cn('h-full rounded', bar)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function StreamId({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex items-center gap-1.5 text-[10px] text-zinc-500">
      <span className="font-semibold uppercase tracking-wide">stream</span>
      <code className="rounded bg-zinc-900 px-1 py-0.5 text-zinc-400 tabular">{value}</code>
      <Tooltip content={copied ? 'Copied' : 'Copy stream id (keep for replay)'}>
        <button
          onClick={() => {
            void navigator.clipboard?.writeText(value).then(() => {
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            });
          }}
          className="rounded p-0.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"
          aria-label="Copy stream id"
        >
          {copied ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
        </button>
      </Tooltip>
    </div>
  );
}

export function EventCard({ event, compact = false }: { event: AgentEvent; compact?: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const Icon = TYPE_ICON[event.type] ?? Activity;
  const sev = SEVERITY_STYLE[event.severity] ?? SEVERITY_STYLE.info;

  return (
    <article
      className={cn(
        'rounded-lg border border-l-2 border-zinc-800 bg-panel p-3 transition-colors hover:border-zinc-700',
        sev.border,
        compact ? 'p-2.5' : 'p-3',
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Icon className={cn('h-3.5 w-3.5 shrink-0', sev.icon)} />
            <Badge variant="outline" className="font-mono text-[10px]">{event.type}</Badge>
            <Badge variant={sev.badge}>{event.severity}</Badge>
            {event.asset && <Badge variant="default">{event.asset}</Badge>}
            {event.venue && <Badge variant="outline">{event.venue}</Badge>}
            {event.instrument && <Badge variant="outline">{event.instrument}</Badge>}
            <span className="text-[11px] text-zinc-600 tabular" title={event.time}>
              {timeAgo(event.time)}
            </span>
          </div>
          <p className={cn('mt-1.5 leading-snug text-zinc-200', compact ? 'text-xs' : 'text-sm')}>{event.summary}</p>
        </div>
        {!compact && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="shrink-0 rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"
            aria-label={expanded ? 'Collapse details' : 'Expand details'}
          >
            {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </button>
        )}
      </div>

      {!compact && expanded && (
        <div className="mt-3 space-y-3 border-t border-zinc-800 pt-3">
          {event.evidence.length > 0 && (
            <ul className="space-y-1">
              {event.evidence.map((ev, i) => (
                <li key={i} className="flex items-center gap-2 text-[11px]">
                  {ev.supports ? (
                    <Check className="h-3 w-3 shrink-0 text-emerald-400" />
                  ) : (
                    <X className="h-3 w-3 shrink-0 text-rose-400" />
                  )}
                  <span className="text-zinc-500">{ev.indicator}</span>
                  <span className="text-zinc-200 tabular">{ev.value}</span>
                </li>
              ))}
            </ul>
          )}
          <MeasurementsBlock label="Observed" data={event.measurements?.observed} />
          <MeasurementsBlock label="Estimated" estimated data={event.measurements?.estimated} />
          {event.confidence != null && <ConfidenceMeter value={event.confidence} />}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
            {event.stream_id && <StreamId value={event.stream_id} />}
            <span className="text-[10px] text-zinc-600" title={`idempotency key: ${event.idempotency_key}`}>
              id {event.id}
            </span>
            {event.scenario_id && (
              <span className="text-[10px] text-zinc-600">scenario {event.scenario_id}</span>
            )}
          </div>
        </div>
      )}
    </article>
  );
}
