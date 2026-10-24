'use client';

import Link from 'next/link';
import { ExternalLink, Star } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import type { NewsItem } from '@/lib/api';
import { timeAgo } from '@/lib/format';
import { cn } from '@/lib/utils';

const KIND_VARIANT: Record<NewsItem['kind'], 'success' | 'warning' | 'info' | 'default'> = {
  verified: 'success',
  rumour: 'warning',
  analysis: 'info',
  opinion: 'default',
};

function SentimentDot({ value }: { value: number | null }) {
  if (value == null) return <span className="h-2 w-2 rounded-full bg-zinc-600" title="sentiment: n/a" />;
  const color = value > 0.1 ? 'bg-emerald-500' : value < -0.1 ? 'bg-rose-500' : 'bg-amber-500';
  return <span className={cn('h-2 w-2 rounded-full', color)} title={`sentiment ${value.toFixed(2)}`} />;
}

function Importance({ value }: { value: number }) {
  return (
    <span className="inline-flex items-center gap-0.5" title={`importance ${value}/5`}>
      {Array.from({ length: 5 }, (_, i) => (
        <Star
          key={i}
          className={cn('h-2.5 w-2.5', i < value ? 'fill-amber-400 text-amber-400' : 'text-zinc-700')}
        />
      ))}
    </span>
  );
}

export function categoryLabel(cat: string): string {
  return cat.replace(/_/g, ' ');
}

export function NewsCard({ item, compact = false }: { item: NewsItem; compact?: boolean }) {
  return (
    <article className="rounded-lg border border-zinc-800 bg-panel p-3 transition-colors hover:border-zinc-700">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <SentimentDot value={item.sentiment} />
            <span className="text-[11px] font-medium text-zinc-400">{item.source}</span>
            <span className="text-[11px] text-zinc-600 tabular">{timeAgo(item.published_at)}</span>
            <Importance value={item.importance} />
          </div>
          <h3 className={cn('mt-1 font-medium leading-snug text-zinc-100', compact ? 'text-xs' : 'text-sm')}>
            {item.source_url ? (
              <a href={item.source_url} target="_blank" rel="noopener noreferrer" className="hover:underline">
                {item.headline}
              </a>
            ) : (
              item.headline
            )}
          </h3>
          {!compact && item.summary && (
            <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-zinc-500">{item.summary}</p>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <Badge variant="default">{categoryLabel(item.category)}</Badge>
            <Badge variant={KIND_VARIANT[item.kind]}>{item.kind}</Badge>
            {item.assets.map((a) => (
              <Link key={a} href={`/crypto/${encodeURIComponent(a)}`}>
                <Badge variant="outline" className="cursor-pointer hover:border-zinc-500 hover:text-zinc-200">
                  {a}
                </Badge>
              </Link>
            ))}
          </div>
        </div>
        {item.source_url && (
          <a
            href={item.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="shrink-0 rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"
            aria-label="Open source"
          >
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
        )}
      </div>
    </article>
  );
}
