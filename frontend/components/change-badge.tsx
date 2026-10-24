import { Minus, TrendingDown, TrendingUp } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatPct } from '@/lib/format';

interface ChangeBadgeProps {
  value: number | null | undefined;
  className?: string;
  showIcon?: boolean;
  digits?: number;
}

/** Signed % chip colored emerald/rose. */
export function ChangeBadge({ value, className, showIcon = true, digits = 2 }: ChangeBadgeProps) {
  if (value == null || !Number.isFinite(value)) {
    return <span className={cn('text-zinc-600 tabular', className)}>—</span>;
  }
  const positive = value > 0;
  const flat = value === 0;
  const Icon = flat ? Minus : positive ? TrendingUp : TrendingDown;
  return (
    <span
      className={cn(
        'inline-flex items-center gap-0.5 tabular',
        flat ? 'text-zinc-400' : positive ? 'text-emerald-400' : 'text-rose-400',
        className,
      )}
    >
      {showIcon && <Icon className="h-3 w-3" />}
      {formatPct(value, digits)}
    </span>
  );
}
