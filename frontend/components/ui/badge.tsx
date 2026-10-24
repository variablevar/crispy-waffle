import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] font-medium leading-none transition-colors',
  {
    variants: {
      variant: {
        default: 'border-zinc-700 bg-zinc-800/60 text-zinc-300',
        outline: 'border-zinc-700 text-zinc-400',
        success: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400',
        destructive: 'border-rose-500/30 bg-rose-500/10 text-rose-400',
        warning: 'border-amber-500/30 bg-amber-500/10 text-amber-400',
        info: 'border-sky-500/30 bg-sky-500/10 text-sky-400',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
