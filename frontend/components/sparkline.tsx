import { cn } from '@/lib/utils';

interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  className?: string;
  /** force a color direction instead of deriving from first->last delta */
  positive?: boolean;
}

/** Hand-rolled SVG polyline sparkline, colored by sign of first->last delta. */
export function Sparkline({ data, width = 96, height = 28, className, positive }: SparklineProps) {
  if (!data || data.length < 2) {
    return <div style={{ width, height }} className={cn('flex items-center justify-center text-[10px] text-zinc-600', className)}>—</div>;
  }
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const pad = 1;
  const stepX = (width - pad * 2) / (data.length - 1);
  const points = data
    .map((v, i) => `${(pad + i * stepX).toFixed(2)},${(height - pad - ((v - min) / range) * (height - pad * 2)).toFixed(2)}`)
    .join(' ');
  const up = positive ?? data[data.length - 1] >= data[0];
  const color = up ? '#10b981' : '#f43f5e';
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className={className} aria-hidden>
      <polyline points={points} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}
