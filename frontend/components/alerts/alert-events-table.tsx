'use client';

import Link from 'next/link';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ErrorState } from '@/components/error-state';
import { EmptyState } from '@/components/empty-state';
import { UnavailableState } from '@/components/unavailable-state';
import { DataFreshness } from '@/components/data-freshness';
import type { AlertEvent, ListResponse } from '@/lib/api';
import { timeAgo } from '@/lib/format';
import { SEVERITY_VARIANT } from './alert-rules-table';

interface AlertEventsTableProps {
  data: ListResponse<AlertEvent> | null;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
}

export function AlertEventsTable({ data, loading, error, onRefresh }: AlertEventsTableProps) {
  if (loading && !data) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-9 w-full" />
        ))}
      </div>
    );
  }
  if (error && !data) return <ErrorState error={error} onRetry={onRefresh} />;
  if (!data) return null;
  if (!data.meta.available) return <UnavailableState />;
  if (data.items.length === 0) return <EmptyState title="No alert events" description="Events appear here when rules trigger." />;

  return (
    <div>
      <div className="mb-2 flex justify-end">
        <DataFreshness updatedAt={data.meta.updated_at} stale={data.meta.stale} available={data.meta.available} />
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Severity</TableHead>
            <TableHead>Type</TableHead>
            <TableHead>Symbol</TableHead>
            <TableHead>Message</TableHead>
            <TableHead>Triggered</TableHead>
            <TableHead>Ack</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.items.map((e) => (
            <TableRow key={e.id}>
              <TableCell><Badge variant={SEVERITY_VARIANT[e.severity]}>{e.severity}</Badge></TableCell>
              <TableCell className="text-zinc-300">{e.type.replace(/_/g, ' ')}</TableCell>
              <TableCell>
                {e.symbol ? (
                  <Link href={`/crypto/${encodeURIComponent(e.symbol)}`} className="text-zinc-200 hover:underline">
                    {e.symbol}
                  </Link>
                ) : (
                  <span className="text-zinc-600">—</span>
                )}
              </TableCell>
              <TableCell className="max-w-md whitespace-normal text-zinc-400">{e.message}</TableCell>
              <TableCell className="text-zinc-500">{timeAgo(e.triggered_at)}</TableCell>
              <TableCell>
                <span
                  className={
                    e.acknowledged
                      ? 'inline-block h-2 w-2 rounded-full bg-zinc-600'
                      : 'inline-block h-2 w-2 rounded-full bg-emerald-400'
                  }
                  title={e.acknowledged ? 'acknowledged' : 'unacknowledged'}
                />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
