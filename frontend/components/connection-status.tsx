'use client';

import { Wifi, WifiOff } from 'lucide-react';
import { Tooltip } from '@/components/ui/tooltip';
import { usePolling } from '@/lib/use-polling';
import type { HealthResponse } from '@/lib/api';
import { formatUptime } from '@/lib/format';
import { cn } from '@/lib/utils';

/** Pings /health every 10s and reports backend connectivity. */
export function ConnectionStatus({ className }: { className?: string }) {
  const { data, error } = usePolling<HealthResponse>('/health', 10000);

  const down = !!error && !data;
  const degraded = data?.status === 'degraded';

  const color = down ? 'text-rose-400' : degraded ? 'text-amber-400' : 'text-emerald-400';
  const label = down ? 'Backend offline' : degraded ? 'Degraded' : 'Connected';

  const detail = down
    ? `Cannot reach the API: ${error}`
    : data
      ? `status: ${data.status} · uptime ${formatUptime(data.uptime_sec)}\n` +
        Object.entries(data.services)
          .map(([k, v]) => `${k}: ${v ? 'ok' : 'down'}`)
          .join('\n')
      : 'Checking…';

  return (
    <Tooltip content={<span className="whitespace-pre-line">{detail}</span>} className={className}>
      <span className={cn('inline-flex items-center gap-1.5 text-[11px]', color)}>
        {down ? <WifiOff className="h-3.5 w-3.5" /> : <Wifi className="h-3.5 w-3.5" />}
        {label}
      </span>
    </Tooltip>
  );
}
