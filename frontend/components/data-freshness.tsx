'use client';

import { useEffect, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { timeAgo } from '@/lib/format';
import { cn } from '@/lib/utils';

interface DataFreshnessProps {
  updatedAt?: string | null;
  stale?: boolean;
  available?: boolean;
  className?: string;
}

/**
 * Freshness indicator: "updated Xs ago" + STALE / unavailable badges driven by
 * the contract's `stale` / `available` fields.
 */
export function DataFreshness({ updatedAt, stale, available = true, className }: DataFreshnessProps) {
  // tick so relative times update
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 5000);
    return () => clearInterval(id);
  }, []);

  if (!available) {
    return <Badge variant="destructive" className={className}>Source unavailable</Badge>;
  }

  return (
    <span className={cn('inline-flex items-center gap-1.5 text-[11px] text-zinc-500 tabular', className)}>
      {updatedAt ? <span>updated {timeAgo(updatedAt)}</span> : <span>updated —</span>}
      {stale && <Badge variant="warning">STALE</Badge>}
    </span>
  );
}
