'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Bell, Droplets, LayoutDashboard, Newspaper, Radar, X, Zap } from 'lucide-react';
import { ConnectionStatus } from '@/components/connection-status';
import { cn } from '@/lib/utils';

const NAV = [
  { href: '/', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/news', label: 'News', icon: Newspaper },
  { href: '/defi', label: 'DeFi', icon: Droplets },
  { href: '/alerts', label: 'Alerts', icon: Bell },
  { href: '/events', label: 'Events', icon: Radar },
];

export function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const pathname = usePathname();

  const content = (
    <div className="flex h-full flex-col">
      <div className="flex h-14 items-center justify-between border-b border-zinc-800 px-4">
        <Link href="/" className="flex items-center gap-2" onClick={onClose}>
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-emerald-500/15">
            <Zap className="h-4 w-4 text-emerald-400" />
          </span>
          <span className="text-sm font-bold tracking-wide text-zinc-100">SkyBus</span>
        </Link>
        <button
          onClick={onClose}
          className="rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200 md:hidden"
          aria-label="Close menu"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <nav className="flex-1 space-y-1 p-3">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = href === '/' ? pathname === '/' : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              onClick={onClose}
              className={cn(
                'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                active ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-100',
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          );
        })}
      </nav>
      <div className="border-t border-zinc-800 p-3">
        <ConnectionStatus />
      </div>
    </div>
  );

  return (
    <>
      {/* mobile drawer */}
      <div
        className={cn(
          'fixed inset-0 z-50 bg-black/70 transition-opacity md:hidden',
          open ? 'opacity-100' : 'pointer-events-none opacity-0',
        )}
        onClick={onClose}
        aria-hidden
      />
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-50 w-64 border-r border-zinc-800 bg-panel transition-transform md:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        {content}
      </aside>
    </>
  );
}
