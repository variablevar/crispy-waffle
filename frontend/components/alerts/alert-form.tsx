'use client';

import { useState } from 'react';
import { BellPlus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { createAlertRule, type AlertType, type Severity } from '@/lib/api';

interface ParamField {
  key: string;
  label: string;
  kind: 'number' | 'direction';
  placeholder?: string;
}

const PARAM_FIELDS: Record<AlertType, ParamField[]> = {
  price_cross: [
    { key: 'threshold', label: 'Price threshold (USDT)', kind: 'number', placeholder: 'e.g. 100000' },
    { key: 'direction', label: 'Direction', kind: 'direction' },
  ],
  liquidity_zone: [
    { key: 'price_low', label: 'Zone low (USDT)', kind: 'number' },
    { key: 'price_high', label: 'Zone high (USDT)', kind: 'number' },
  ],
  liquidity_sweep: [],
  book_imbalance: [{ key: 'threshold', label: 'Imbalance threshold (-1..1)', kind: 'number', placeholder: 'e.g. 0.4' }],
  oi_spike: [{ key: 'threshold_pct', label: 'OI change (%)', kind: 'number', placeholder: 'e.g. 5' }],
  funding_extreme: [{ key: 'threshold', label: 'Funding rate (decimal)', kind: 'number', placeholder: 'e.g. 0.0005' }],
  volume_spike: [{ key: 'threshold_pct', label: 'Volume change (%)', kind: 'number', placeholder: 'e.g. 100' }],
  liquidation_burst: [{ key: 'threshold_usd', label: 'Liquidations (USD)', kind: 'number', placeholder: 'e.g. 5000000' }],
  breaking_news: [],
  trend_change: [],
  cross_exchange_divergence: [{ key: 'threshold_bps', label: 'Divergence (bps)', kind: 'number', placeholder: 'e.g. 25' }],
};

const ALERT_TYPES: AlertType[] = [
  'price_cross',
  'liquidity_zone',
  'liquidity_sweep',
  'book_imbalance',
  'oi_spike',
  'funding_extreme',
  'volume_spike',
  'liquidation_burst',
  'breaking_news',
  'trend_change',
  'cross_exchange_divergence',
];

const SYMBOL_LESS_TYPES: AlertType[] = ['breaking_news'];

export function AlertForm({ defaultSymbol, onCreated }: { defaultSymbol?: string; onCreated?: () => void }) {
  const [type, setType] = useState<AlertType>('price_cross');
  const [symbol, setSymbol] = useState(defaultSymbol ?? '');
  const [params, setParams] = useState<Record<string, string>>({});
  const [severity, setSeverity] = useState<Severity>('info');
  const [cooldown, setCooldown] = useState('300');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const fields = PARAM_FIELDS[type];
  const needsSymbol = !SYMBOL_LESS_TYPES.includes(type);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setSuccess(false);
    try {
      const parsed: Record<string, number | string> = {};
      for (const f of fields) {
        const raw = params[f.key];
        if (raw == null || raw === '') continue;
        parsed[f.key] = f.kind === 'number' ? Number(raw) : raw;
      }
      await createAlertRule({
        type,
        symbol: needsSymbol && symbol ? symbol.toUpperCase() : undefined,
        params: parsed,
        severity,
        cooldown_sec: Number(cooldown) || 300,
      });
      setSuccess(true);
      setParams({});
      onCreated?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create alert');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BellPlus className="h-4 w-4 text-zinc-500" /> Create alert
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <label className="space-y-1">
            <span className="text-[11px] uppercase tracking-wider text-zinc-500">Type</span>
            <Select
              value={type}
              onChange={(e) => {
                setType(e.target.value as AlertType);
                setParams({});
              }}
            >
              {ALERT_TYPES.map((t) => (
                <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>
              ))}
            </Select>
          </label>
          {needsSymbol && (
            <label className="space-y-1">
              <span className="text-[11px] uppercase tracking-wider text-zinc-500">Symbol</span>
              <Input
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                placeholder="BTC"
                required
              />
            </label>
          )}
          {fields.map((f) => (
            <label key={f.key} className="space-y-1">
              <span className="text-[11px] uppercase tracking-wider text-zinc-500">{f.label}</span>
              {f.kind === 'direction' ? (
                <Select
                  value={params[f.key] ?? 'above'}
                  onChange={(e) => setParams((p) => ({ ...p, [f.key]: e.target.value }))}
                >
                  <option value="above">above</option>
                  <option value="below">below</option>
                </Select>
              ) : (
                <Input
                  type="number"
                  step="any"
                  value={params[f.key] ?? ''}
                  placeholder={f.placeholder}
                  onChange={(e) => setParams((p) => ({ ...p, [f.key]: e.target.value }))}
                  required
                />
              )}
            </label>
          ))}
          <label className="space-y-1">
            <span className="text-[11px] uppercase tracking-wider text-zinc-500">Severity</span>
            <Select value={severity} onChange={(e) => setSeverity(e.target.value as Severity)}>
              <option value="info">info</option>
              <option value="warning">warning</option>
              <option value="critical">critical</option>
            </Select>
          </label>
          <label className="space-y-1">
            <span className="text-[11px] uppercase tracking-wider text-zinc-500">Cooldown (sec)</span>
            <Input type="number" min={0} value={cooldown} onChange={(e) => setCooldown(e.target.value)} />
          </label>
          <div className="flex items-end">
            <Button type="submit" disabled={submitting} className="w-full sm:w-auto">
              {submitting ? 'Creating…' : 'Create rule'}
            </Button>
          </div>
        </form>
        {error && <p className="mt-3 text-xs text-rose-400">{error}</p>}
        {success && <p className="mt-3 text-xs text-emerald-400">Alert rule created.</p>}
      </CardContent>
    </Card>
  );
}
