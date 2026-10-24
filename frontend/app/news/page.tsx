'use client';

import { useState } from 'react';
import { Newspaper, Rss, Server } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { NewsCard, categoryLabel } from '@/components/news-card';
import { ErrorState } from '@/components/error-state';
import { EmptyState } from '@/components/empty-state';
import { UnavailableState } from '@/components/unavailable-state';
import { DataFreshness } from '@/components/data-freshness';
import { usePolling } from '@/lib/use-polling';
import { getNews, type ListResponse, type NewsCategory, type NewsItem, type NewsKind, type NewsSourcesResponse } from '@/lib/api';
import { timeAgo } from '@/lib/format';
import { cn } from '@/lib/utils';

const PAGE_SIZE = 30;
const KINDS: NewsKind[] = ['verified', 'opinion', 'rumour', 'analysis'];

function SourcesPanel() {
  const { data, error, loading, refresh } = usePolling<NewsSourcesResponse>('/news/sources', 60000);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="flex items-center gap-2">
          <Server className="h-4 w-4 text-zinc-500" /> Sources
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1.5">
        {loading && !data ? (
          <Skeleton className="h-16 w-full" />
        ) : error && !data ? (
          <ErrorState error={error} onRetry={refresh} compact />
        ) : !data ? null : data.sources.length === 0 ? (
          <p className="text-xs text-zinc-500">No sources configured.</p>
        ) : (
          data.sources.map((s) => (
            <div key={s.name} className="flex items-center gap-2 text-xs">
              <span
                className={cn(
                  'h-2 w-2 shrink-0 rounded-full',
                  s.error ? 'bg-rose-500' : s.configured ? 'bg-emerald-500' : 'bg-zinc-600',
                )}
                title={s.error ?? (s.configured ? 'configured' : 'not configured')}
              />
              <span className="font-medium text-zinc-300">{s.name}</span>
              <span className="ml-auto text-[10px] text-zinc-600 tabular">
                {s.error ? 'error' : s.last_fetch ? timeAgo(s.last_fetch) : 'never fetched'}
              </span>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

export default function NewsPage() {
  const [category, setCategory] = useState<string>('');
  const [kind, setKind] = useState<string>('');
  const [asset, setAsset] = useState<string>('');
  const [offset, setOffset] = useState(0);
  const [extraItems, setExtraItems] = useState<NewsItem[]>([]);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(true);

  const qs = new URLSearchParams();
  if (category) qs.set('category', category);
  if (kind) qs.set('kind', kind);
  if (asset.trim()) qs.set('asset', asset.trim().toUpperCase());
  qs.set('limit', String(PAGE_SIZE));
  qs.set('offset', '0');

  const { data, error, loading, refresh } = usePolling<ListResponse<NewsItem>>(`/news?${qs.toString()}`, 60000);
  const categoriesRes = usePolling<{ categories: NewsCategory[] }>('/news/categories', 300000);

  const items = [...(data?.items ?? []), ...extraItems];
  const derivedCategories = Array.from(new Set(items.map((n) => n.category))).sort();
  const categories = categoriesRes.data?.categories ?? derivedCategories;

  function resetPaging() {
    setOffset(0);
    setExtraItems([]);
    setHasMore(true);
    setLoadMoreError(null);
  }

  async function loadMore() {
    const nextOffset = offset + PAGE_SIZE;
    setLoadingMore(true);
    setLoadMoreError(null);
    try {
      const res = await getNews({
        category: category || undefined,
        kind: kind || undefined,
        asset: asset.trim() ? asset.trim().toUpperCase() : undefined,
        limit: PAGE_SIZE,
        offset: nextOffset,
      });
      setExtraItems((prev) => [...prev, ...res.items]);
      setOffset(nextOffset);
      if (res.items.length < PAGE_SIZE) setHasMore(false);
    } catch (e) {
      setLoadMoreError(e instanceof Error ? e.message : 'Failed to load more');
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="flex items-center gap-2 text-lg font-bold text-zinc-100">
          <Newspaper className="h-5 w-5 text-zinc-500" /> News feed
        </h1>
        <p className="text-xs text-zinc-500">Aggregated crypto news with sentiment &amp; importance scoring</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-4">
        <div className="space-y-4 lg:col-span-3">
          {/* filters */}
          <Card>
            <CardContent className="space-y-3 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={() => {
                    setCategory('');
                    resetPaging();
                  }}
                >
                  <Badge variant={category === '' ? 'info' : 'outline'} className="cursor-pointer">all categories</Badge>
                </button>
                {categories.map((c) => (
                  <button
                    key={c}
                    onClick={() => {
                      setCategory(c);
                      resetPaging();
                    }}
                  >
                    <Badge variant={category === c ? 'info' : 'outline'} className="cursor-pointer">
                      {categoryLabel(c)}
                    </Badge>
                  </button>
                ))}
              </div>
              <div className="flex flex-wrap gap-3">
                <Select
                  value={kind}
                  onChange={(e) => {
                    setKind(e.target.value);
                    resetPaging();
                  }}
                  className="w-40"
                >
                  <option value="">all kinds</option>
                  {KINDS.map((k) => (
                    <option key={k} value={k}>{k}</option>
                  ))}
                </Select>
                <Input
                  value={asset}
                  onChange={(e) => {
                    setAsset(e.target.value);
                    resetPaging();
                  }}
                  placeholder="Filter by asset (e.g. BTC)"
                  className="w-48"
                />
                {data && (
                  <span className="ml-auto self-center">
                    <DataFreshness updatedAt={data.meta.updated_at} stale={data.meta.stale} available={data.meta.available} />
                  </span>
                )}
              </div>
            </CardContent>
          </Card>

          {/* feed */}
          {loading && !data ? (
            <div className="space-y-2">
              {Array.from({ length: 5 }, (_, i) => <Skeleton key={i} className="h-24 w-full" />)}
            </div>
          ) : error && !data ? (
            <ErrorState error={error} onRetry={refresh} />
          ) : !data ? null : !data.meta.available ? (
            <UnavailableState />
          ) : items.length === 0 ? (
            <EmptyState title="No news found" description="Try widening the filters." icon={<Rss className="h-6 w-6" />} />
          ) : (
            <div className="space-y-2">
              {items.map((item) => <NewsCard key={item.id} item={item} />)}
              <div className="flex flex-col items-center gap-2 pt-2">
                {loadMoreError && <p className="text-xs text-rose-400">{loadMoreError}</p>}
                {hasMore && (
                  <Button variant="outline" onClick={loadMore} disabled={loadingMore}>
                    {loadingMore ? 'Loading…' : 'Load more'}
                  </Button>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="space-y-4">
          <SourcesPanel />
        </div>
      </div>
    </div>
  );
}
