'use client';

import { cn } from '@/lib/utils';

interface ImbalanceMeterProps {
  value: number | null; // -1..1
  className?: string;
  leftLabel?: string;
  rightLabel?: string;
}

/** Diverging meter for values in [-1, 1] (book/liquidity imbalance). */
export function ImbalanceMeter({ value, className, leftLabel = 'sell', rightLabel = 'buy' }: ImbalanceMeterProps) {
  const v = value == null ? null : Math.max(-1, Math.min(1, value));
  return (
    <div className={cn('w-full', className)}>
      <div className="relative h-2.5 w-full overflow-hidden rounded-full bg-zinc-800">
        {/* center marker */}
        <div className="absolute left-1/2 top-0 h-full w-px bg-zinc-600" />
        {v != null && v !== 0 && (
          <div
            className={cn('absolute top-0 h-full', v > 0 ? 'bg-emerald-500' : 'bg-rose-500')}
            style={{
              left: v > 0 ? '50%' : `${50 + v * 50}%`,
              width: `${Math.abs(v) * 50}%`,
            }}
          />
        )}
      </div>
      <div className="mt-1 flex items-center justify-between text-[10px] text-zinc-500">
        <span className="text-rose-400/80">{leftLabel} -1</span>
        <span className="tabular font-medium text-zinc-300">{v == null ? '—' : v.toFixed(2)}</span>
        <span className="text-emerald-400/80">+1 {rightLabel}</span>
      </div>
    </div>
  );
}
