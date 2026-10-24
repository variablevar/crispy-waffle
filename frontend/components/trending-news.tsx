'use client';

import { Newspaper, Rss } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { NewsCard } from '@/components/news-card';
import { ErrorState } from '@/components/error-state';
import { EmptyState } from '@/components/empty-state';
import { UnavailableState } from '@/components/unavailable-state';
import { DataFreshness } from '@/components/data-freshness';
import { usePolling } from '@/lib/use-polling';
import type { ListResponse, NewsItem } from '@/lib/api';

/** Trending news panel used on the dashboard. */
export function TrendingNews({ limit = 8 }: { limit?: number }) {
  const { data, error, loading, refresh } = usePolling<ListResponse<NewsItem>>(`/news?limit=${limit}`, 60000);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="flex items-center gap-2">
          <Newspaper className="h-4 w-4 text-zinc-500" /> Trending news
        </CardTitle>
        {data && <DataFreshness updatedAt={data.meta.updated_at} stale={data.meta.stale} available={data.meta.available} />}
      </CardHeader>
      <CardContent className="space-y-2">
        {loading && !data ? (
          Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-20 w-full" />)
        ) : error && !data ? (
          <ErrorState error={error} onRetry={refresh} compact />
        ) : !data ? null : !data.meta.available ? (
          <UnavailableState />
        ) : data.items.length === 0 ? (
          <EmptyState title="No news" description="No recent news items." icon={<Rss className="h-6 w-6" />} />
        ) : (
          data.items.map((item) => <NewsCard key={item.id} item={item} compact />)
        )}
      </CardContent>
    </Card>
  );
}
