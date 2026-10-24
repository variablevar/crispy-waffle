'use client';

import * as React from 'react';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

interface DialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title?: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
}

export function Dialog({ open, onOpenChange, title, description, children, className }: DialogProps) {
  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onOpenChange(false);
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onOpenChange]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={() => onOpenChange(false)}
        aria-hidden
      />
      <div
        role="dialog"
        aria-modal="true"
        className={cn(
          'relative z-10 w-full max-w-md rounded-lg border border-zinc-800 bg-panel p-5 shadow-xl',
          className,
        )}
      >
        <button
          onClick={() => onOpenChange(false)}
          className="absolute right-3 top-3 rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"
          aria-label="Close"
        >
          <X className="h-4 w-4" />
        </button>
        {title && <h2 className="mb-1 text-sm font-semibold text-zinc-100">{title}</h2>}
        {description && <p className="mb-3 text-xs text-zinc-500">{description}</p>}
        {children}
      </div>
    </div>
  );
}
