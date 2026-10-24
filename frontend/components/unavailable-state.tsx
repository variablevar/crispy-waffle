import { WifiOff } from 'lucide-react';
import { cn } from '@/lib/utils';

interface UnavailableStateProps {
  reason?: string;
  className?: string;
}

/** Rendered when the API reports available:false — never show fabricated values. */
export function UnavailableState({ reason, className }: UnavailableStateProps) {
  return (
    <div className={cn('flex flex-col items-center justify-center gap-2 rounded-lg border border-amber-500/20 bg-amber-500/5 p-6 text-center', className)}>
      <WifiOff className="h-5 w-5 text-amber-400" />
      <p className="text-xs font-medium text-amber-300">Source unavailable</p>
      <p className="max-w-md text-[11px] text-zinc-500">
        {reason ?? 'The upstream data source for this panel is currently unavailable. No values are shown to avoid displaying fabricated data.'}
      </p>
    </div>
  );
}
