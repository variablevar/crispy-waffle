import * as React from 'react';
import { cn } from '@/lib/utils';

/** Scroll-area-lite: a div with styled thin scrollbars. */
export function ScrollArea({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn('scrollarea overflow-auto', className)} {...props}>
      {children}
    </div>
  );
}
