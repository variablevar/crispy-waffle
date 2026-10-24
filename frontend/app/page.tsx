'use client';

import { Activity, Bitcoin, Coins, Layers } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { StatCard } from '@/components/stat-card';
import { ChangeBadge } from '@/components/change-badge';
import { DataFreshness } from '@/components/data-freshness';
import { ErrorState } from '@/components/error-state';
import { FearGreedGauge } from '@/components/fear-greed-gauge';
import { CoinTable } from '@/components/coin-table';
import { MoversStrip } from '@/components/movers-strip';
import { TrendingNews } from '@/components/trending-news';
import { AgentActivityPanel } from '@/components/agent-activity-panel';
import { usePolling } from '@/lib/use-polling';
import type { MarketOverview } from '@/lib/api';
import { formatNumber, formatUSD } from '@/lib/format';

function MarketOverviewCards() {
  const { data, error, loading, refresh } = usePolling<MarketOverview>('/market/overview', 60000);

  if (loading && !data) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-24 w-full" />
        ))}
      </div>
    );
  }
  if (error && !data) return <ErrorState error={error} onRetry={refresh} />;
  if (!data) return null;

  return (
    <div className="space-y-2">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Total market cap"
          value={formatUSD(data.total_market_cap)}
          icon={<Layers className="h-4 w-4" />}
          change={<ChangeBadge value={data.market_cap_change_24h_pct} />}
          footer={data.active_cryptocurrencies != null ? `${formatNumber(data.active_cryptocurrencies, 0)} active assets` : undefined}
        />
        <StatCard
          title="24h volume"
          value={formatUSD(data.total_volume_24h)}
          icon={<Activity className="h-4 w-4" />}
        />
        <StatCard
          title="BTC dominance"
          value={data.btc_dominance == null ? '—' : `${data.btc_dominance.toFixed(1)}%`}
          icon={<Bitcoin className="h-4 w-4" />}
        />
        <StatCard
          title="ETH dominance"
          value={data.eth_dominance == null ? '—' : `${data.eth_dominance.toFixed(1)}%`}
          icon={<Coins className="h-4 w-4" />}
        />
      </div>
      <div className="flex justify-end">
        <DataFreshness updatedAt={data.updated_at} stale={data.stale} />
      </div>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-bold text-zinc-100">Market dashboard</h1>
        <p className="text-xs text-zinc-500">Global crypto market intelligence</p>
      </div>

      <MarketOverviewCards />

      <div className="grid gap-4 lg:grid-cols-3">
        <FearGreedGauge />
        <div className="lg:col-span-2">
          <MoversStrip />
        </div>
      </div>

      <AgentActivityPanel limit={5} />

      <Card>
        <CardHeader className="pb-0">
          <CardTitle>Market leaders</CardTitle>
        </CardHeader>
        <CardContent className="pt-4">
          <Tabs defaultValue="mcap">
            <TabsList>
              <TabsTrigger value="mcap">Top 10 by market cap</TabsTrigger>
              <TabsTrigger value="volume">Top 10 by volume (non-stablecoin)</TabsTrigger>
            </TabsList>
            <TabsContent value="mcap">
              <CoinTable url="/market/top?limit=10" />
            </TabsContent>
            <TabsContent value="volume">
              <CoinTable url="/market/top-volume?limit=10" />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>

      <TrendingNews limit={8} />
    </div>
  );
}
