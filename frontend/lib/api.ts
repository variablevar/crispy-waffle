// Typed API client for the SkyBus backend (see docs/API_CONTRACT.md).
// All requests go through the Next.js rewrite proxy: /api/:path* -> BACKEND_INTERNAL_URL/api/:path*.

export const API_BASE = '/api/v1';

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new ApiError(res.status, `API ${res.status}${text ? `: ${text.slice(0, 200)}` : ''}`);
  }
  return (await res.json()) as T;
}

// ---------- Contract enums / types ----------

export type Timeframe = '15m' | '1h' | '4h' | '1d' | '1w';
export type Trend = 'bullish' | 'bearish' | 'neutral';
export type NewsKind = 'verified' | 'opinion' | 'rumour' | 'analysis';
export type NewsCategory =
  | 'halving' | 'token_unlock' | 'token_burn' | 'exchange_listing' | 'delisting'
  | 'binance_update' | 'bybit_update' | 'regulation' | 'etf' | 'whale' | 'hack'
  | 'protocol_upgrade' | 'defi' | 'liquidity' | 'macro' | 'partnership' | 'general';
export type ZoneType =
  | 'observed_bid_wall' | 'observed_ask_wall'
  | 'estimated_liquidation' | 'estimated_support' | 'estimated_resistance';
export type ScenarioType =
  | 'bullish_breakout' | 'bearish_sweep' | 'short_squeeze' | 'long_squeeze' | 'no_trade';
export type AlertType =
  | 'price_cross' | 'liquidity_zone' | 'liquidity_sweep' | 'book_imbalance' | 'oi_spike'
  | 'funding_extreme' | 'volume_spike' | 'liquidation_burst' | 'breaking_news'
  | 'trend_change' | 'cross_exchange_divergence';
export type Severity = 'info' | 'warning' | 'critical';

export interface ListMeta {
  source?: string[];
  updated_at: string | null;
  stale: boolean;
  available: boolean;
}

export interface ListResponse<T> {
  items: T[];
  meta: ListMeta;
}

export interface SentimentSummary {
  score: number;
  label: string;
}

export interface CoinSummary {
  id: string;
  symbol: string;
  name: string;
  image: string | null;
  price: number | null;
  change_1h: number | null;
  change_24h: number | null;
  change_7d: number | null;
  market_cap: number | null;
  volume_24h: number | null;
  circulating_supply: number | null;
  dominance: number | null;
  sparkline: number[];
  trend: Trend;
  sentiment: SentimentSummary | null;
  news_count_24h: number;
  updated_at: string;
  stale: boolean;
}

export interface CoinDetail extends CoinSummary {
  description: string | null;
  ath: number | null;
  atl: number | null;
  ath_change_pct: number | null;
  total_volume: number | null;
  market_cap_rank: number | null;
  homepage: string | null;
}

export interface Candle {
  time: number; // unix seconds
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface ExchangeTicker {
  exchange: 'binance' | 'bybit';
  instrument: 'spot' | 'usdt_perp';
  symbol: string;
  price: number | null;
  bid: number | null;
  ask: number | null;
  spread_bps: number | null;
  volume_24h: number | null;
  funding_rate: number | null;
  open_interest: number | null;
  updated_at: string;
  stale: boolean;
}

export interface NewsItem {
  id: string;
  headline: string;
  source: string;
  source_url: string | null;
  published_at: string;
  assets: string[];
  category: NewsCategory;
  sentiment: number | null;
  importance: number; // 1..5
  kind: NewsKind;
  summary: string | null;
}

export interface FearGreed {
  value: number;
  classification: string;
  source: 'alternative.me';
  attribution: string;
  history: { value: number; timestamp: string }[];
  updated_at: string;
  stale: boolean;
}

export interface PressureReport {
  symbol: string;
  taker_buy_volume: number | null;
  taker_sell_volume: number | null;
  taker_ratio: number | null;
  cvd: { time: number; value: number }[];
  book_imbalance: number | null;
  spot_vs_futures: { spot_ratio: number | null; futures_ratio: number | null };
  timeframes: Record<string, { buy: number | null; sell: number | null; ratio: number | null }>;
  methodology: string;
  confidence: 'high' | 'medium' | 'low';
  updated_at: string;
  stale: boolean;
}

export interface DerivativesReport {
  symbol: string;
  funding: {
    binance: number | null;
    bybit: number | null;
    history: { time: number; exchange: string; value: number }[];
  };
  open_interest: {
    binance: number | null;
    bybit: number | null;
    history: { time: number; value: number }[];
  };
  long_short_ratio: { binance: number | null; bybit: number | null } | null;
  basis: number | null;
  liquidations: {
    available: boolean;
    source: string;
    note: string;
    recent: { time: number; side: string; size_usd: number; exchange: string }[];
  };
  updated_at: string;
  stale: boolean;
}

export interface LiquidityZone {
  price_low: number;
  price_high: number;
  type: ZoneType;
  strength: number; // 0..1
  size_usd: number | null;
  exchange: string | null;
  label: string;
  source: string;
}

export interface LiquidityReport {
  symbol: string;
  mid_price: number | null;
  walls: {
    bids: { price: number; size_usd: number; exchange: string }[];
    asks: { price: number; size_usd: number; exchange: string }[];
  };
  zones: LiquidityZone[];
  heatmap: {
    price_points: number[];
    time_points: number[];
    intensity: number[][];
  } | null;
  imbalance: number | null;
  disclaimer: string;
  updated_at: string;
  stale: boolean;
}

export interface Scenario {
  id: string;
  type: ScenarioType;
  asset: string;
  title: string;
  bias: 'long' | 'short' | 'none';
  trigger_conditions: string[];
  confirmation_signals: string[];
  invalidation_conditions: string[];
  target_zones: { price_low: number; price_high: number; label: string }[];
  risks: string[];
  evidence: { indicator: string; value: string; supports: boolean }[];
  confidence: number; // 0..1
  methodology: string;
  generated_at: string;
  stale: boolean;
}

export interface ScenariosResponse {
  scenarios: Scenario[];
  market_state: Record<string, string>;
  updated_at: string;
  stale: boolean;
}

export interface Pool {
  dex: string;
  chain: string;
  pair: string;
  liquidity_usd: number | null;
  volume_24h: number | null;
  price_usd: number | null;
  price_change_24h: number | null;
  url: string | null;
}

export interface AlertRule {
  id: string;
  user_key: string;
  type: AlertType;
  symbol: string | null;
  params: Record<string, number | string>;
  severity: Severity;
  cooldown_sec: number;
  active: boolean;
  created_at: string;
}

export interface AlertEvent {
  id: string;
  rule_id: string | null;
  type: AlertType;
  symbol: string | null;
  severity: Severity;
  message: string;
  triggered_at: string;
  acknowledged: boolean;
}

export interface MarketOverview {
  total_market_cap: number | null;
  total_volume_24h: number | null;
  btc_dominance: number | null;
  eth_dominance: number | null;
  market_cap_change_24h_pct: number | null;
  active_cryptocurrencies: number | null;
  updated_at: string;
  stale: boolean;
}

export interface ChartResponse {
  candles: Candle[];
  source: string;
  updated_at: string;
  stale: boolean;
}

export interface SentimentReport {
  asset_score: number | null;
  label: string;
  components: {
    news: number | null;
    momentum: number | null;
    volume: number | null;
    funding: number | null;
  };
  market_fear_greed: FearGreed | null;
  disclaimer: string;
  updated_at: string;
  stale: boolean;
}

export interface DefiResponse {
  pools: Pool[];
  tvl_usd: number | null;
  source: string[];
  updated_at: string;
  stale: boolean;
}

export interface NewsSourcesResponse {
  sources: {
    name: string;
    configured: boolean;
    last_fetch: string | null;
    error: string | null;
  }[];
}

export interface HealthResponse {
  status: 'ok' | 'degraded';
  services: {
    redis: boolean;
    database: boolean;
    binance_ws: boolean;
    bybit_ws: boolean;
    coingecko: boolean;
  };
  uptime_sec: number;
}

// ---------- Typed fetchers (one per endpoint) ----------

export const getMarketOverview = () => apiFetch<MarketOverview>('/market/overview');
export const getMarketTop = (limit = 10) => apiFetch<ListResponse<CoinSummary>>(`/market/top?limit=${limit}`);
export const getMarketTopVolume = (limit = 10) => apiFetch<ListResponse<CoinSummary>>(`/market/top-volume?limit=${limit}`);
export const getMarketMovers = (type: 'gainers' | 'losers' | 'volume', limit = 5) =>
  apiFetch<ListResponse<CoinSummary>>(`/market/movers?type=${type}&limit=${limit}`);
export const getFearGreed = () => apiFetch<FearGreed>('/market/fear-greed');

export const getCoin = (symbol: string) => apiFetch<CoinDetail>(`/coins/${symbol}`);
export const getCoinChart = (symbol: string, timeframe: Timeframe) =>
  apiFetch<ChartResponse>(`/coins/${symbol}/chart?timeframe=${timeframe}&source=auto`);
export const getCoinTickers = (symbol: string) => apiFetch<ListResponse<ExchangeTicker>>(`/coins/${symbol}/tickers`);
export const getCoinPressure = (symbol: string) => apiFetch<PressureReport>(`/coins/${symbol}/pressure`);
export const getCoinDerivatives = (symbol: string) => apiFetch<DerivativesReport>(`/coins/${symbol}/derivatives`);
export const getCoinLiquidity = (symbol: string) => apiFetch<LiquidityReport>(`/coins/${symbol}/liquidity`);
export const getCoinScenarios = (symbol: string) => apiFetch<ScenariosResponse>(`/coins/${symbol}/scenarios`);
export const getCoinSentiment = (symbol: string) => apiFetch<SentimentReport>(`/coins/${symbol}/sentiment`);
export const getCoinDefi = (symbol: string) => apiFetch<DefiResponse>(`/coins/${symbol}/defi`);
export const getCoinNews = (symbol: string, limit = 20) =>
  apiFetch<ListResponse<NewsItem>>(`/coins/${symbol}/news?limit=${limit}`);

export interface NewsQuery {
  category?: string;
  asset?: string;
  kind?: string;
  limit?: number;
  offset?: number;
}
export const getNews = (q: NewsQuery = {}) => {
  const params = new URLSearchParams();
  if (q.category) params.set('category', q.category);
  if (q.asset) params.set('asset', q.asset);
  if (q.kind) params.set('kind', q.kind);
  if (q.limit != null) params.set('limit', String(q.limit));
  if (q.offset != null) params.set('offset', String(q.offset));
  const qs = params.toString();
  return apiFetch<ListResponse<NewsItem>>(`/news${qs ? `?${qs}` : ''}`);
};
export const getNewsCategories = () => apiFetch<{ categories: NewsCategory[] }>('/news/categories');
export const getNewsSources = () => apiFetch<NewsSourcesResponse>('/news/sources');

export const createAlertRule = (body: {
  type: AlertType;
  symbol?: string;
  params: Record<string, number | string>;
  severity?: Severity;
  cooldown_sec?: number;
}) =>
  apiFetch<AlertRule>('/alerts', { method: 'POST', body: JSON.stringify(body) });
export const getAlertRules = () => apiFetch<ListResponse<AlertRule>>('/alerts');
export const deleteAlertRule = (id: string) =>
  apiFetch<{ deleted: boolean }>(`/alerts/${id}`, { method: 'DELETE' });
export const getAlertEvents = (limit = 50) => apiFetch<ListResponse<AlertEvent>>(`/alerts/events?limit=${limit}`);

export const getHealth = () => apiFetch<HealthResponse>('/health');

export { apiFetch };
