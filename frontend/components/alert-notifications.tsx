'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { Bell } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { usePolling } from '@/lib/use-polling';
import type { AlertEvent, ListResponse, Severity } from '@/lib/api';
import { timeAgo } from '@/lib/format';
import { cn } from '@/lib/utils';

const SEVERITY_VARIANT: Record<Severity, 'info' | 'warning' | 'destructive'> = {
  info: 'info',
  warning: 'warning',
  critical: 'destructive',
};

/** In-app notification bell fed by polling /alerts/events?limit=10. */
export function AlertNotifications() {
  const { data } = usePolling<ListResponse<AlertEvent>>('/alerts/events?limit=10', 15000);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [open]);

  const events = data?.items ?? [];
  const unack = events.filter((e) => !e.acknowledged).length;

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="relative rounded-md p-2 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
        aria-label="Alert notifications"
      >
        <Bell className="h-4 w-4" />
        {unack > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500 px-1 text-[9px] font-bold text-white tabular">
            {unack}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 top-full z-50 mt-2 w-80 rounded-lg border border-zinc-800 bg-panel shadow-xl">
          <div className="flex items-center justify-between border-b border-zinc-800 px-3 py-2">
            <span className="text-xs font-semibold text-zinc-200">Recent alert events</span>
            <Link href="/alerts" className="text-[11px] text-zinc-500 hover:text-zinc-300" onClick={() => setOpen(false)}>
              View all
            </Link>
          </div>
          <div className="scrollarea max-h-80 overflow-auto">
            {events.length === 0 ? (
              <p className="p-4 text-center text-xs text-zinc-500">No alert events yet</p>
            ) : (
              events.map((e) => (
                <div key={e.id} className="border-b border-zinc-800/60 px-3 py-2 last:border-0">
                  <div className="flex items-center gap-2">
                    <Badge variant={SEVERITY_VARIANT[e.severity]}>{e.severity}</Badge>
                    {e.symbol && (
                      <Link
                        href={`/crypto/${encodeURIComponent(e.symbol)}`}
                        className="text-[11px] font-medium text-zinc-300 hover:underline"
                        onClick={() => setOpen(false)}
                      >
                        {e.symbol}
                      </Link>
                    )}
                    <span className="ml-auto text-[10px] text-zinc-600 tabular">{timeAgo(e.triggered_at)}</span>
                  </div>
                  <p className={cn('mt-1 text-[11px] leading-snug', e.acknowledged ? 'text-zinc-500' : 'text-zinc-300')}>
                    {e.message}
                  </p>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
