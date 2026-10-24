'use client';

import { Bell, Gauge, Layers, LineChart, Newspaper, Scale, Activity, GitBranch, FlaskConical } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { CoinHeader } from '@/components/coin/coin-header';
import { OverviewTab } from '@/components/coin/overview-tab';
import { CoinNewsTab } from '@/components/coin/coin-news-tab';
import { PriceChart } from '@/components/price-chart';
import { IndicatorsTab } from '@/components/coin/indicators-tab';
import { PressureTab } from '@/components/coin/pressure-tab';
import { DerivativesTab } from '@/components/coin/derivatives-tab';
import { LiquidityTab } from '@/components/coin/liquidity-tab';
import { ScenariosTab } from '@/components/coin/scenarios-tab';
import { CoinAlertsTab } from '@/components/coin/coin-alerts-tab';

const TAB_DEFS = [
  { value: 'overview', label: 'Overview', icon: Layers },
  { value: 'news', label: 'News', icon: Newspaper },
  { value: 'chart', label: 'Chart', icon: LineChart },
  { value: 'indicators', label: 'Indicators', icon: Activity },
  { value: 'pressure', label: 'Pressure', icon: Gauge },
  { value: 'derivatives', label: 'Derivatives', icon: Scale },
  { value: 'liquidity', label: 'Liquidity', icon: GitBranch },
  { value: 'scenarios', label: 'Scenarios', icon: FlaskConical },
  { value: 'alerts', label: 'Alerts', icon: Bell },
] as const;

export function CoinPageClient({ symbol }: { symbol: string }) {
  return (
    <div className="space-y-4">
      <CoinHeader symbol={symbol} />
      <Tabs defaultValue="overview">
        <div className="scrollarea overflow-x-auto">
          <TabsList className="w-max">
            {TAB_DEFS.map(({ value, label, icon: Icon }) => (
              <TabsTrigger key={value} value={value}>
                <Icon className="h-3.5 w-3.5" />
                {label}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
        <TabsContent value="overview"><OverviewTab symbol={symbol} /></TabsContent>
        <TabsContent value="news"><CoinNewsTab symbol={symbol} /></TabsContent>
        <TabsContent value="chart"><PriceChart symbol={symbol} /></TabsContent>
        <TabsContent value="indicators"><IndicatorsTab symbol={symbol} /></TabsContent>
        <TabsContent value="pressure"><PressureTab symbol={symbol} /></TabsContent>
        <TabsContent value="derivatives"><DerivativesTab symbol={symbol} /></TabsContent>
        <TabsContent value="liquidity"><LiquidityTab symbol={symbol} /></TabsContent>
        <TabsContent value="scenarios"><ScenariosTab symbol={symbol} /></TabsContent>
        <TabsContent value="alerts"><CoinAlertsTab symbol={symbol} /></TabsContent>
      </Tabs>
    </div>
  );
}
