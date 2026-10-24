import * as React from 'react';
import { cn } from '@/lib/utils';

interface TooltipProps {
  content: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

/** Lightweight CSS-only tooltip. */
export function Tooltip({ content, children, className }: TooltipProps) {
  return (
    <span className={cn('group/tip relative inline-flex items-center', className)}>
      {children}
      <span
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 hidden w-64 -translate-x-1/2 whitespace-normal rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-left text-xs font-normal leading-relaxed text-zinc-300 shadow-lg group-hover/tip:block"
      >
        {content}
      </span>
    </span>
  );
}
