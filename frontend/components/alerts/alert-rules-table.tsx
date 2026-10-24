'use client';

import { useState } from 'react';
import { Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog } from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tooltip } from '@/components/ui/tooltip';
import { ErrorState } from '@/components/error-state';
import { EmptyState } from '@/components/empty-state';
import { UnavailableState } from '@/components/unavailable-state';
import { DataFreshness } from '@/components/data-freshness';
import { deleteAlertRule, type AlertRule, type ListResponse, type Severity } from '@/lib/api';
import { timeAgo } from '@/lib/format';

export const SEVERITY_VARIANT: Record<Severity, 'info' | 'warning' | 'destructive'> = {
  info: 'info',
  warning: 'warning',
  critical: 'destructive',
};

function paramsSummary(params: Record<string, number | string>): string {
  const entries = Object.entries(params);
  if (entries.length === 0) return '—';
  return entries.map(([k, v]) => `${k}=${v}`).join(' ');
}

interface AlertRulesTableProps {
  data: ListResponse<AlertRule> | null;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
}

export function AlertRulesTable({ data, loading, error, onRefresh }: AlertRulesTableProps) {
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  async function doDelete() {
    if (!confirmId) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteAlertRule(confirmId);
      setConfirmId(null);
      onRefresh();
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : 'Delete failed');
    } finally {
      setDeleting(false);
    }
  }

  if (loading && !data) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }, (_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    );
  }
  if (error && !data) return <ErrorState error={error} onRetry={onRefresh} />;
  if (!data) return null;
  if (!data.meta.available) return <UnavailableState />;
  if (data.items.length === 0) return <EmptyState title="No alert rules" description="Create a rule above to start monitoring." />;

  return (
    <div>
      <div className="mb-2 flex justify-end">
        <DataFreshness updatedAt={data.meta.updated_at} stale={data.meta.stale} available={data.meta.available} />
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Type</TableHead>
            <TableHead>Symbol</TableHead>
            <TableHead>Params</TableHead>
            <TableHead>Severity</TableHead>
            <TableHead className="text-right">Cooldown</TableHead>
            <TableHead>Active</TableHead>
            <TableHead>Created</TableHead>
            <TableHead className="w-10" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.items.map((rule) => (
            <TableRow key={rule.id}>
              <TableCell className="font-medium text-zinc-200">{rule.type.replace(/_/g, ' ')}</TableCell>
              <TableCell>{rule.symbol ?? <span className="text-zinc-600">any</span>}</TableCell>
              <TableCell className="max-w-52 truncate text-zinc-400" title={paramsSummary(rule.params)}>
                {paramsSummary(rule.params)}
              </TableCell>
              <TableCell><Badge variant={SEVERITY_VARIANT[rule.severity]}>{rule.severity}</Badge></TableCell>
              <TableCell className="text-right">{rule.cooldown_sec}s</TableCell>
              <TableCell>
                {/* Contract v1 exposes no PATCH endpoint for toggling rules. */}
                <Tooltip content="The API contract (v1) does not expose an endpoint to toggle rules; delete and recreate instead.">
                  <Badge variant={rule.active ? 'success' : 'default'} className="cursor-help">
                    {rule.active ? 'active' : 'inactive'}
                  </Badge>
                </Tooltip>
              </TableCell>
              <TableCell className="text-zinc-500">{timeAgo(rule.created_at)}</TableCell>
              <TableCell>
                <Button variant="ghost" size="icon" onClick={() => setConfirmId(rule.id)} aria-label="Delete rule">
                  <Trash2 className="h-3.5 w-3.5 text-zinc-500" />
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <Dialog
        open={confirmId != null}
        onOpenChange={(open) => {
          if (!open) {
            setConfirmId(null);
            setDeleteError(null);
          }
        }}
        title="Delete alert rule"
        description="This permanently removes the rule. This action cannot be undone."
      >
        {deleteError && <p className="mb-3 text-xs text-rose-400">{deleteError}</p>}
        <div className="flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={() => setConfirmId(null)}>Cancel</Button>
          <Button variant="destructive" size="sm" onClick={doDelete} disabled={deleting}>
            {deleting ? 'Deleting…' : 'Delete'}
          </Button>
        </div>
      </Dialog>
    </div>
  );
}
