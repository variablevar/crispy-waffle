import { Minus, TrendingDown, TrendingUp } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import type { Trend } from '@/lib/api';
import { cn } from '@/lib/utils';

export function TrendBadge({ trend, className }: { trend: Trend; className?: string }) {
  if (trend === 'bullish') {
    return (
      <Badge variant="success" className={className}>
        <TrendingUp className="h-3 w-3" /> bullish
      </Badge>
    );
  }
  if (trend === 'bearish') {
    return (
      <Badge variant="destructive" className={className}>
        <TrendingDown className="h-3 w-3" /> bearish
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className={cn('text-zinc-400', className)}>
      <Minus className="h-3 w-3" /> neutral
    </Badge>
  );
}
