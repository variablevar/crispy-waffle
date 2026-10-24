'use client';

import { AlertTriangle, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface ErrorStateProps {
  error?: string | null;
  onRetry?: () => void;
  className?: string;
  compact?: boolean;
}

export function ErrorState({ error, onRetry, className, compact }: ErrorStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-2 rounded-lg border border-rose-500/20 bg-rose-500/5 text-center',
        compact ? 'p-3' : 'p-8',
        className,
      )}
    >
      <AlertTriangle className={cn('text-rose-400', compact ? 'h-4 w-4' : 'h-6 w-6')} />
      <p className="text-xs font-medium text-rose-300">Failed to load data</p>
      {error && <p className="max-w-md break-words text-[11px] text-zinc-500">{error}</p>}
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry} className="mt-1">
          <RotateCcw className="h-3 w-3" /> Retry
        </Button>
      )}
    </div>
  );
}
