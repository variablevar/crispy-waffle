# Methodology & Data-Quality Notes

This document explains how SkyBus computes each indicator, what is **observed** vs
**estimated**, and the known limitations. The API surfaces the same caveats inline
(`methodology`, `disclaimer`, `note`, and `label` fields); this is the long-form version.

## 1. Data provenance and staleness

Every payload carries `updated_at` and `stale`. A payload is marked `stale` when it is
served from cache after its TTL because the upstream fetch failed. When a source has
never delivered data (missing API key, unreachable feed, unsupported instrument), the
endpoint returns `available: false` and the UI renders an explicit *Source unavailable*
state. **No numeric field is ever fabricated.**

## 2. Buying / selling pressure engine

- **Taker buy/sell volume** comes from exchange-reported aggressive-side trade data
  (Binance `aggTrades` maker flag, Bybit `publicTrade` side, plus the Binance taker
  buy/sell volume REST endpoint for cross-checks).
- **Taker ratio** = taker buy volume / taker sell volume over a rolling window.
- **CVD** (Cumulative Volume Delta) = running sum of (taker buy − taker sell) in quote
  currency, per exchange and aggregated.
- **Book imbalance** = (bid depth − ask depth) / (bid depth + ask depth) over the top N
  levels of the order book snapshots; range −1..1.
- **What this does NOT mean:** every trade has a buyer and a seller. Taker flow measures
  *aggression* (who crossed the spread), never a count of buyers vs sellers. The UI and
  API methodology strings state this explicitly.
- Confidence is `high` when both exchanges stream fresh trade data, `medium` with one
  exchange, `low` when derived from REST snapshots only.

## 3. Liquidity intelligence

- **Observed** walls and concentration are computed from live order-book snapshots
  (Binance depth / Bybit orderbook): levels whose resting size exceeds N× the median
  level size are flagged as walls. These are directly observed exchange data.
- **Estimated liquidation clusters** are a *model*: we combine open interest, funding
  sign, and typical retail leverage buckets to estimate where forced-closure pressure
  may concentrate. They are always labelled `ESTIMATED — …` with `source:
  "estimation_model"`. Private stop-loss orders are **not observable** and are never
  presented as data.
- If a CoinGlass premium key is configured, reported liquidation data replaces part of
  the model and is labelled with its source. Without it, the liquidation panel shows
  exchange-reported force-order streams (where the exchange publishes them) plus the
  labelled estimation model.

## 4. Scenario engine

Rule-based, deterministic, explainable. Each scenario is generated only from indicators
with fresh data, and carries: trigger conditions, confirmation signals, invalidation
conditions, target zones, risks, per-indicator evidence, a 0..1 confidence score and a
methodology string. Missing or conflicting inputs produce a `no_trade` scenario rather
than a directional guess. Touching an estimated liquidation zone is never, by itself, a
signal. The engine handles cross-product cases (spot vs futures flow divergence,
price/OI quadrants, funding vs price divergence, cross-exchange non-confirmation,
correlated-asset divergence) by requiring agreement across independent indicators
before assigning directional confidence.

**Not financial advice.** The engine is educational market-structure analysis.

## 5. Sentiment

- The market-wide Fear & Greed index comes from alternative.me and is always shown with
  attribution.
- The per-asset sentiment score is a proprietary composite (news lexicon sentiment,
  price momentum, volume behaviour, funding). It is explicitly labelled as such and
  never presented as "the Fear & Greed Index".

## 6. News pipeline

Sources: NewsData.io and GNews when keys are configured, plus public RSS feeds and
exchange announcement feeds. Articles are deduplicated by normalized-headline
similarity (≥0.85 → same story; earliest kept, asset mentions merged). Each item is
categorized by keyword rules into the contract categories, scored for importance (1–5)
and assigned a lexicon-based sentiment estimate. Items are classified as `verified`
(official announcements/wires), `opinion`, `rumour`, or `analysis`. When no news source
is configured or reachable, the feed shows the unavailable state — news is never
invented.

## 7. Backtesting & signal validation

The scenario engine records generated scenarios to the database (when available) so
outcomes can be evaluated later against realized prices — with no look-ahead (only data
≤ generation time may be used). Fees, slippage and funding must be included in any
evaluation. Historical order-book depth is generally **not** available from free APIs,
so backtests of liquidity-based scenarios are limited by data availability; the UI and
docs state this limitation rather than inventing performance numbers.

## 8. AMM vs order-book liquidity

DEX pool liquidity (DEX Screener / DefiLlama / GeckoTerminal) is structurally different
from centralized order-book depth. The UI keeps them in separate panels and never sums
them into one "liquidity" number.

## 9. Event detectors (agent stream)

The agent event stream (`/api/v1/agent/stream`) is produced by deterministic detectors
running over the same LiveState/caches as the REST API — never from simulated inputs:

- Funding extremes, OI spikes, long/short ratios come from the derivatives poller cache.
- CVD divergence and taker-flow shifts come from observed exchange trades.
- Zone approach/breach/cross events compare live prices against the liquidity engine's
  zones; zones derived from the estimation model stay labelled `ESTIMATED` in event
  measurements (`measurements.estimated`), separate from `measurements.observed`.
- Liquidation bursts fire only from exchange force-order streams; where no feed exists,
  no event is ever synthesized.
- `DATA_STALE` / `DATA_RECOVERED` report the health of SkyBus's own feeds.
- `SCENARIO_CREATED` / `SCENARIO_INVALIDATED` are diffs of consecutive ScenarioV2
  engine outputs; the first pass after startup is a silent baseline (no event flood).

Events are persisted to a Redis Stream (durable, replayable, MAXLEN-trimmed) with an
in-process ring-buffer fallback that is explicitly reported via
`GET /api/v1/agent/system/health` (`event_stream.backend`). Idempotency keys make
repeat delivery safe for consumers.
