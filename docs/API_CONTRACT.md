# SkyBus API Contract (v1)

Single source of truth for backend routes and frontend consumption.
Base URL: `/api/v1`. All timestamps are ISO-8601 UTC strings. All money/price
values are JSON numbers (never strings). Every payload that reflects external
data includes `updated_at` (ISO string) and `stale` (boolean). When a data
source is unavailable, endpoints still return HTTP 200 with an
`available: false` field (or an empty list plus `available: false` in `meta`)
— never fabricated values.

Common wrapper for list endpoints:

```json
{ "items": [], "meta": { "source": ["coingecko"], "updated_at": "...", "stale": false, "available": true } }
```

## Enums

- `timeframe`: `15m | 1h | 4h | 1d | 1w`
- `trend`: `bullish | bearish | neutral`
- `news_kind`: `verified | opinion | rumour | analysis`
- `news_category`: `halving | token_unlock | token_burn | exchange_listing | delisting | binance_update | bybit_update | regulation | etf | whale | hack | protocol_upgrade | defi | liquidity | macro | partnership | general`
- `zone_type`: `observed_bid_wall | observed_ask_wall | estimated_liquidation | estimated_support | estimated_resistance`
- `scenario_type`: `bullish_breakout | bearish_sweep | short_squeeze | long_squeeze | no_trade`
- `alert_type`: `price_cross | liquidity_zone | liquidity_sweep | book_imbalance | oi_spike | funding_extreme | volume_spike | liquidation_burst | breaking_news | trend_change | cross_exchange_divergence`
- `severity`: `info | warning | critical`

## Types

```ts
CoinSummary = {
  id: string;              // coingecko id, e.g. "bitcoin"
  symbol: string;          // "BTC" (uppercase)
  name: string;
  image: string | null;
  price: number | null;
  change_1h: number | null;   // percent
  change_24h: number | null;
  change_7d: number | null;
  market_cap: number | null;
  volume_24h: number | null;
  circulating_supply: number | null;
  dominance: number | null;   // percent of total market cap
  sparkline: number[];        // 7d hourly closes, may be []
  trend: "bullish"|"bearish"|"neutral";
  sentiment: { score: number; label: string } | null; // score -1..1, proprietary
  news_count_24h: number;
  updated_at: string; stale: boolean;
}

CoinDetail = CoinSummary & {
  description: string | null;
  ath: number | null; atl: number | null;
  ath_change_pct: number | null;
  total_volume: number | null;
  market_cap_rank: number | null;
  homepage: string | null;
}

Candle = { time: number; open: number; high: number; low: number; close: number; volume: number } // time = unix seconds

ExchangeTicker = {
  exchange: "binance" | "bybit";
  instrument: "spot" | "usdt_perp";
  symbol: string;            // e.g. "BTCUSDT"
  price: number | null;
  bid: number | null; ask: number | null; spread_bps: number | null;
  volume_24h: number | null;
  funding_rate: number | null;       // perp only
  open_interest: number | null;      // perp only, in base asset
  updated_at: string; stale: boolean;
}

NewsItem = {
  id: string;
  headline: string;
  source: string;            // publisher name
  source_url: string | null;
  published_at: string;
  assets: string[];          // ["BTC","ETH"]
  category: news_category;
  sentiment: number | null;  // -1..1 estimate
  importance: number;        // 1..5
  kind: news_kind;
  summary: string | null;
}

FearGreed = {
  value: number; classification: string; // alternative.me values
  source: "alternative.me"; attribution: string;
  history: { value: number; timestamp: string }[];
  updated_at: string; stale: boolean;
}

PressureReport = {
  symbol: string;
  taker_buy_volume: number | null;   // quote USDT, window
  taker_sell_volume: number | null;
  taker_ratio: number | null;        // buy/sell
  cvd: { time: number; value: number }[];
  book_imbalance: number | null;     // -1..1, top-of-book depth weighted
  spot_vs_futures: { spot_ratio: number | null; futures_ratio: number | null };
  timeframes: { [tf: string]: { buy: number | null; sell: number | null; ratio: number | null } };
  methodology: string;
  confidence: "high" | "medium" | "low";
  updated_at: string; stale: boolean;
}

DerivativesReport = {
  symbol: string;
  funding: { binance: number | null; bybit: number | null; history: { time: number; exchange: string; value: number }[] };
  open_interest: { binance: number | null; bybit: number | null; history: { time: number; value: number }[] };
  long_short_ratio: { binance: number | null; bybit: number | null } | null;
  basis: number | null;              // perp - spot, USDT
  liquidations: { available: boolean; source: string; note: string; recent: { time: number; side: string; size_usd: number; exchange: string }[] };
  updated_at: string; stale: boolean;
}

LiquidityZone = {
  price_low: number; price_high: number;
  type: zone_type;
  strength: number;            // 0..1 normalized
  size_usd: number | null;
  exchange: string | null;     // null = aggregated/model
  label: string;               // e.g. "ESTIMATED — short liquidation cluster"
  source: string;              // "binance_orderbook" | "estimation_model" | ...
}

LiquidityReport = {
  symbol: string;
  mid_price: number | null;
  walls: { bids: { price: number; size_usd: number; exchange: string }[]; asks: { price: number; size_usd: number; exchange: string }[] };
  zones: LiquidityZone[];
  heatmap: { price_points: number[]; time_points: number[]; intensity: number[][] } | null;
  imbalance: number | null;
  disclaimer: string;          // explains observed vs estimated
  updated_at: string; stale: boolean;
}

Scenario = {
  id: string;
  type: scenario_type;
  asset: string;
  title: string;
  bias: "long" | "short" | "none";
  trigger_conditions: string[];
  confirmation_signals: string[];
  invalidation_conditions: string[];
  target_zones: { price_low: number; price_high: number; label: string }[];
  risks: string[];
  evidence: { indicator: string; value: string; supports: boolean }[];
  confidence: number;          // 0..1
  methodology: string;
  generated_at: string; stale: boolean;
}

Pool = {
  dex: string; chain: string; pair: string;
  liquidity_usd: number | null; volume_24h: number | null;
  price_usd: number | null; price_change_24h: number | null;
  url: string | null;
}

AlertRule = {
  id: string; user_key: string;
  type: alert_type; symbol: string | null;
  params: Record<string, number | string>;
  severity: severity; cooldown_sec: number;
  active: boolean; created_at: string;
}

AlertEvent = {
  id: string; rule_id: string | null; type: alert_type;
  symbol: string | null; severity: severity;
  message: string; triggered_at: string; acknowledged: boolean;
}
```

## Endpoints

### Market
- `GET /market/overview` → `{ total_market_cap, total_volume_24h, btc_dominance, eth_dominance, market_cap_change_24h_pct, active_cryptocurrencies, updated_at, stale }`
- `GET /market/top?limit=10` → list wrapper of `CoinSummary` (top by market cap)
- `GET /market/top-volume?limit=10` → list wrapper of `CoinSummary` (non-stablecoins by 24h volume)
- `GET /market/movers?type=gainers|losers|volume&limit=5` → list wrapper of `CoinSummary`
- `GET /market/fear-greed` → `FearGreed`

### Coins
- `GET /coins/{symbol}` → `CoinDetail` (404 if unknown)
- `GET /coins/{symbol}/chart?timeframe=1h|4h|1d|1w&source=auto` → `{ candles: Candle[], source: string, updated_at, stale }`
- `GET /coins/{symbol}/tickers` → list wrapper of `ExchangeTicker`
- `GET /coins/{symbol}/pressure` → `PressureReport`
- `GET /coins/{symbol}/derivatives` → `DerivativesReport`
- `GET /coins/{symbol}/liquidity` → `LiquidityReport`
- `GET /coins/{symbol}/scenarios` → `{ scenarios: Scenario[], market_state: Record<string, string>, updated_at, stale }`
- `GET /coins/{symbol}/sentiment` → `{ asset_score: number|null, label: string, components: { news: number|null, momentum: number|null, volume: number|null, funding: number|null }, market_fear_greed: FearGreed|null, disclaimer: string, updated_at, stale }`
- `GET /coins/{symbol}/defi` → `{ pools: Pool[], tvl_usd: number|null, source: string[], updated_at, stale }`
- `GET /coins/{symbol}/news?limit=20` → list wrapper of `NewsItem`

### News
- `GET /news?category=&asset=&kind=&limit=30&offset=0` → list wrapper of `NewsItem`
- `GET /news/categories` → `{ categories: news_category[] }`
- `GET /news/sources` → `{ sources: { name: string; configured: boolean; last_fetch: string|null; error: string|null }[] }`

### Alerts
- `POST /alerts` body `{ type, symbol?, params, severity?, cooldown_sec? }` → `AlertRule`
- `GET /alerts` → list wrapper of `AlertRule`
- `DELETE /alerts/{id}` → `{ deleted: true }`
- `GET /alerts/events?limit=50` → list wrapper of `AlertEvent`

### System
- `GET /health` → `{ status: "ok"|"degraded", services: { redis: bool, database: bool, binance_ws: bool, bybit_ws: bool, coingecko: bool }, uptime_sec: number }`
- `WS  /ws` → server-push JSON messages `{ topic: "price"|"alert"|"news", data: any }`. Optional; frontend must work without it (polling).

## Notes
- Symbol params are uppercase base tickers (`BTC`, `ETH`). Backend maps to exchange pairs.
- Rate limiting: backend caches all upstream calls; frontend polls at ≥5s for live panels, ≥60s for market tables.
