import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import { SiteShell } from '@/components/site-shell';
import './globals.css';

const inter = Inter({ subsets: ['latin'], variable: '--font-inter' });

export const metadata: Metadata = {
  title: 'SkyBus — Crypto Intelligence Terminal',
  description: 'Professional crypto news & trading intelligence terminal',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`dark ${inter.variable}`}>
      <body className="font-sans">
        <SiteShell>{children}</SiteShell>
      </body>
    </html>
  );
}
