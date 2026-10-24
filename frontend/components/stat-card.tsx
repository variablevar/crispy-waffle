import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';

interface StatCardProps {
  title: string;
  value: React.ReactNode;
  icon?: React.ReactNode;
  change?: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
}

export function StatCard({ title, value, icon, change, footer, className }: StatCardProps) {
  return (
    <Card className={cn('overflow-hidden', className)}>
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-medium uppercase tracking-wider text-zinc-500">{title}</span>
          {icon && <span className="text-zinc-600">{icon}</span>}
        </div>
        <div className="mt-2 flex items-baseline gap-2">
          <span className="text-xl font-semibold tabular text-zinc-100">{value}</span>
          {change}
        </div>
        {footer && <div className="mt-2 text-[11px] text-zinc-500">{footer}</div>}
      </CardContent>
    </Card>
  );
}
