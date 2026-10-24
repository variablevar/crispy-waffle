import * as React from 'react';
import { cn } from '@/lib/utils';

const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      ref={ref}
      className={cn(
        'flex h-9 w-full rounded-md border border-zinc-700 bg-zinc-900/60 px-3 py-1 text-sm text-zinc-100 shadow-sm transition-colors placeholder:text-zinc-500 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-500 disabled:cursor-not-allowed disabled:opacity-50 tabular',
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = 'Input';

export { Input };
