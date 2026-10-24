'use client';

import { AlertForm } from '@/components/alerts/alert-form';
import { AlertRulesTable } from '@/components/alerts/alert-rules-table';
import { usePolling } from '@/lib/use-polling';
import type { AlertRule, ListResponse } from '@/lib/api';

export function CoinAlertsTab({ symbol }: { symbol: string }) {
  const { data, error, loading, refresh } = usePolling<ListResponse<AlertRule>>('/alerts', 30000);

  const filtered: ListResponse<AlertRule> | null = data
    ? { ...data, items: data.items.filter((r) => r.symbol == null || r.symbol === symbol) }
    : null;

  return (
    <div className="space-y-4">
      <AlertForm defaultSymbol={symbol} onCreated={refresh} />
      <div>
        <h3 className="mb-2 text-sm font-semibold text-zinc-200">Rules for {symbol}</h3>
        <AlertRulesTable data={filtered} loading={loading} error={error} onRefresh={refresh} />
      </div>
    </div>
  );
}
