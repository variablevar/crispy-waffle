'use client';

import { useState } from 'react';
import { NewsCard } from '@/components/news-card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { ErrorState } from '@/components/error-state';
import { EmptyState } from '@/components/empty-state';
import { UnavailableState } from '@/components/unavailable-state';
import { DataFreshness } from '@/components/data-freshness';
import { usePolling } from '@/lib/use-polling';
import type { ListResponse, NewsCategory, NewsItem } from '@/lib/api';
import { cn } from '@/lib/utils';

export function CoinNewsTab({ symbol }: { symbol: string }) {
  const { data, error, loading, refresh } = usePolling<ListResponse<NewsItem>>(
    `/coins/${encodeURIComponent(symbol)}/news?limit=30`,
    60000,
  );
  const [category, setCategory] = useState<NewsCategory | null>(null);

  if (loading && !data) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-24 w-full" />)}
      </div>
    );
  }
  if (error && !data) return <ErrorState error={error} onRetry={refresh} />;
  if (!data) return null;
  if (!data.meta.available) return <UnavailableState />;

  const categories = Array.from(new Set(data.items.map((n) => n.category)));
  const items = category ? data.items.filter((n) => n.category === category) : data.items;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <button onClick={() => setCategory(null)}>
          <Badge variant={category === null ? 'info' : 'outline'} className="cursor-pointer">all</Badge>
        </button>
        {categories.map((c) => (
          <button key={c} onClick={() => setCategory(c)}>
            <Badge variant={category === c ? 'info' : 'outline'} className={cn('cursor-pointer')}>
              {c.replace(/_/g, ' ')}
            </Badge>
          </button>
        ))}
        <span className="ml-auto">
          <DataFreshness updatedAt={data.meta.updated_at} stale={data.meta.stale} available={data.meta.available} />
        </span>
      </div>
      {items.length === 0 ? (
        <EmptyState title="No news" description={category ? `No ${category.replace(/_/g, ' ')} news for ${symbol}.` : `No recent news for ${symbol}.`} />
      ) : (
        <div className="space-y-2">
          {items.map((item) => <NewsCard key={item.id} item={item} />)}
        </div>
      )}
    </div>
  );
}
