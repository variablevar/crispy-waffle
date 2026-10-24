'use client';

import { useState } from 'react';
import { Menu, Zap } from 'lucide-react';
import { Sidebar } from '@/components/sidebar';
import { AlertNotifications } from '@/components/alert-notifications';

export function SiteShell({ children }: { children: React.ReactNode }) {
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <div className="min-h-screen bg-background text-zinc-100">
      {/* mobile top bar */}
      <div className="sticky top-0 z-40 flex h-14 items-center justify-between border-b border-zinc-800 bg-panel/95 px-4 backdrop-blur md:hidden">
        <button
          onClick={() => setDrawerOpen(true)}
          className="rounded p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
          aria-label="Open menu"
        >
          <Menu className="h-5 w-5" />
        </button>
        <span className="flex items-center gap-2 text-sm font-bold">
          <Zap className="h-4 w-4 text-emerald-400" /> SkyBus
        </span>
        <AlertNotifications />
      </div>

      <Sidebar open={drawerOpen} onClose={() => setDrawerOpen(false)} />

      <div className="md:pl-64">
        {/* desktop header */}
        <header className="sticky top-0 z-30 hidden h-12 items-center justify-end border-b border-zinc-800 bg-background/90 px-6 backdrop-blur md:flex">
          <AlertNotifications />
        </header>
        <main className="mx-auto max-w-[1400px] p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
