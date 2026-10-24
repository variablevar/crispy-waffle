// Client-side technical indicators computed from chart candles.

export interface Ohlc {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

/** Simple moving average series; null until enough data. */
export function smaSeries(values: number[], period: number): (number | null)[] {
  const out: (number | null)[] = new Array(values.length).fill(null);
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= period) sum -= values[i - period];
    if (i >= period - 1) out[i] = sum / period;
  }
  return out;
}

/** Exponential moving average series; null until enough data. */
export function emaSeries(values: number[], period: number): (number | null)[] {
  const out: (number | null)[] = new Array(values.length).fill(null);
  if (values.length < period) return out;
  const k = 2 / (period + 1);
  let ema = 0;
  for (let i = 0; i < period; i++) ema += values[i];
  ema /= period;
  out[period - 1] = ema;
  for (let i = period; i < values.length; i++) {
    ema = values[i] * k + ema * (1 - k);
    out[i] = ema;
  }
  return out;
}

/** Wilder RSI series; null until enough data. */
export function rsiSeries(closes: number[], period = 14): (number | null)[] {
  const out: (number | null)[] = new Array(closes.length).fill(null);
  if (closes.length <= period) return out;
  let gain = 0;
  let loss = 0;
  for (let i = 1; i <= period; i++) {
    const diff = closes[i] - closes[i - 1];
    if (diff >= 0) gain += diff;
    else loss -= diff;
  }
  let avgGain = gain / period;
  let avgLoss = loss / period;
  out[period] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  for (let i = period + 1; i < closes.length; i++) {
    const diff = closes[i] - closes[i - 1];
    const g = diff > 0 ? diff : 0;
    const l = diff < 0 ? -diff : 0;
    avgGain = (avgGain * (period - 1) + g) / period;
    avgLoss = (avgLoss * (period - 1) + l) / period;
    out[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  }
  return out;
}

export interface MacdResult {
  macd: (number | null)[];
  signal: (number | null)[];
  histogram: (number | null)[];
}

/** MACD (default 12/26/9). */
export function macdSeries(closes: number[], fast = 12, slow = 26, signalPeriod = 9): MacdResult {
  const emaFast = emaSeries(closes, fast);
  const emaSlow = emaSeries(closes, slow);
  const macd: (number | null)[] = closes.map((_, i) =>
    emaFast[i] != null && emaSlow[i] != null ? (emaFast[i] as number) - (emaSlow[i] as number) : null,
  );
  const macdValues = macd.filter((v): v is number => v != null);
  const signalRaw = emaSeries(macdValues, signalPeriod);
  const offset = macd.length - macdValues.length;
  const signal: (number | null)[] = new Array(macd.length).fill(null);
  for (let i = 0; i < signalRaw.length; i++) signal[offset + i] = signalRaw[i];
  const histogram: (number | null)[] = macd.map((v, i) =>
    v != null && signal[i] != null ? v - (signal[i] as number) : null,
  );
  return { macd, signal, histogram };
}

export interface BollingerResult {
  upper: number | null;
  middle: number | null;
  lower: number | null;
  percentB: number | null;
}

/** Latest Bollinger band values (default 20, 2σ). */
export function bollinger(closes: number[], period = 20, mult = 2): BollingerResult {
  if (closes.length < period) return { upper: null, middle: null, lower: null, percentB: null };
  const window = closes.slice(-period);
  const mean = window.reduce((a, b) => a + b, 0) / period;
  const variance = window.reduce((a, b) => a + (b - mean) ** 2, 0) / period;
  const sd = Math.sqrt(variance);
  const upper = mean + mult * sd;
  const lower = mean - mult * sd;
  const last = closes[closes.length - 1];
  const percentB = upper === lower ? null : (last - lower) / (upper - lower);
  return { upper, middle: mean, lower, percentB };
}

export function lastValue(series: (number | null)[]): number | null {
  for (let i = series.length - 1; i >= 0; i--) {
    if (series[i] != null) return series[i];
  }
  return null;
}
