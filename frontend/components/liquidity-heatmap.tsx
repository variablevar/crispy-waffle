'use client';

import { useEffect, useRef } from 'react';
import { formatUSD } from '@/lib/format';

interface LiquidityHeatmapProps {
  pricePoints: number[];
  timePoints: number[];
  /** intensity[row][col], rows aligned with pricePoints */
  intensity: number[][];
  height?: number;
}

/** Canvas-rendered liquidity heatmap grid. */
export function LiquidityHeatmap({ pricePoints, timePoints, intensity, height = 260 }: LiquidityHeatmapProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const parent = canvas.parentElement;
    if (!parent) return;

    const render = () => {
      const width = parent.clientWidth;
      const dpr = window.devicePixelRatio || 1;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.scale(dpr, dpr);
      ctx.clearRect(0, 0, width, height);

      const rows = pricePoints.length;
      const cols = timePoints.length;
      if (rows === 0 || cols === 0) return;

      let max = 0;
      for (const row of intensity) for (const v of row) if (v > max) max = v;
      if (max <= 0) max = 1;

      const labelW = 64;
      const labelH = 18;
      const gridW = width - labelW;
      const gridH = height - labelH;
      const cellW = gridW / cols;
      const cellH = gridH / rows;

      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const v = intensity[r]?.[c] ?? 0;
          const a = Math.min(1, v / max);
          if (a <= 0.02) continue;
          // emerald -> amber -> rose ramp by intensity
          const hue = 160 - a * 160; // 160 (emerald) to 0 (rose)
          ctx.fillStyle = `hsla(${hue}, 80%, 50%, ${0.12 + a * 0.75})`;
          // price_points usually ascending; draw highest price at top
          const y = gridH - (r + 1) * cellH;
          ctx.fillRect(c * cellW, y, Math.max(1, cellW - 1), Math.max(1, cellH - 1));
        }
      }

      // price axis (right)
      ctx.fillStyle = '#71717a';
      ctx.font = '9px ui-monospace, monospace';
      ctx.textAlign = 'left';
      const ticks = 5;
      for (let i = 0; i <= ticks; i++) {
        const idx = Math.round((i / ticks) * (rows - 1));
        const y = gridH - (idx + 0.5) * cellH;
        ctx.fillText(formatUSD(pricePoints[idx]), gridW + 4, y + 3);
      }
      // time axis (bottom)
      ctx.textAlign = 'center';
      for (let i = 0; i <= 4; i++) {
        const idx = Math.round((i / 4) * (cols - 1));
        const t = timePoints[idx];
        const label = new Date(t * 1000).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
        ctx.fillText(label, idx * cellW + cellW / 2, height - 5);
      }
    };

    render();
    const observer = new ResizeObserver(render);
    observer.observe(parent);
    return () => observer.disconnect();
  }, [pricePoints, timePoints, intensity, height]);

  return (
    <div className="w-full">
      <canvas ref={canvasRef} className="block w-full" />
      <div className="mt-1 flex items-center justify-between text-[10px] text-zinc-600">
        <span>low intensity</span>
        <span>high intensity</span>
      </div>
    </div>
  );
}
