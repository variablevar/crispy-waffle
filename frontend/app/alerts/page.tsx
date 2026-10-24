'use client';

import { Bell } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { AlertForm } from '@/components/alerts/alert-form';
import { AlertRulesTable } from '@/components/alerts/alert-rules-table';
import { AlertEventsTable } from '@/components/alerts/alert-events-table';
import { usePolling } from '@/lib/use-polling';
import type { AlertEvent, AlertRule, ListResponse } from '@/lib/api';

export default function AlertsPage() {
  const rules = usePolling<ListResponse<AlertRule>>('/alerts', 30000);
  const events = usePolling<ListResponse<AlertEvent>>('/alerts/events?limit=50', 15000);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="flex items-center gap-2 text-lg font-bold text-zinc-100">
          <Bell className="h-5 w-5 text-zinc-500" /> Alerts
        </h1>
        <p className="text-xs text-zinc-500">Rule-based alert engine — create rules, review triggered events</p>
      </div>

      <AlertForm onCreated={rules.refresh} />

      <Card>
        <CardHeader><CardTitle>Rules</CardTitle></CardHeader>
        <CardContent>
          <AlertRulesTable data={rules.data} loading={rules.loading} error={rules.error} onRefresh={rules.refresh} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Event history</CardTitle></CardHeader>
        <CardContent>
          <AlertEventsTable data={events.data} loading={events.loading} error={events.error} onRefresh={events.refresh} />
        </CardContent>
      </Card>
    </div>
  );
}
