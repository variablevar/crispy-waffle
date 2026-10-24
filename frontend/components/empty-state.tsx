import { Inbox } from 'lucide-react';
import { cn } from '@/lib/utils';

interface EmptyStateProps {
  title?: string;
  description?: string;
  icon?: React.ReactNode;
  className?: string;
}

export function EmptyState({ title = 'No data', description, icon, className }: EmptyStateProps) {
  return (
    <div className={cn('flex flex-col items-center justify-center gap-2 rounded-lg border border-zinc-800 bg-panel-2/40 p-8 text-center', className)}>
      <span className="text-zinc-600">{icon ?? <Inbox className="h-6 w-6" />}</span>
      <p className="text-xs font-medium text-zinc-400">{title}</p>
      {description && <p className="max-w-md text-[11px] text-zinc-500">{description}</p>}
    </div>
  );
}
