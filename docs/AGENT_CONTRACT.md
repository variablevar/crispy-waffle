# SkyBus Agent Contract v1

Machine-consumption contract for GT Quant and other authorized agent consumers.
This document is the single source of truth for the agent REST API, the event
stream, the `skybus-client` package and the MCP server. Human dashboard routes
(`/api/v1/market/*`, `/api/v1/coins/*`, …) are unchanged and remain public.

Base: `/api/v1/agent`. Auth: `X-API-Key: <key>` header on every agent endpoint
(REST + WS). Keys are configured server-side (`AGENT_API_KEYS` env:
`name:key,name2:key2`), scoped (`read`, `stream`), rate-limited (token bucket,
default 120 req/min/key) and audited. Responses `401` on missing/invalid key,
`403` on insufficient scope, `429` on rate-limit (with `Retry-After`).

## Envelope

Every agent response is a versioned envelope:

```json
{
  "schema_version": "agent.v1",
  "request_id": "01J…",            // ULID, also in X-Request-ID response header
  "observed_at": "ISO-8601|null",  // timestamp of the underlying observation
  "processed_at": "ISO-8601",      // when the server produced this response
  "freshness_sec": 4.2,            // processed_at - observed_at (null if observed_at null)
  "stale": false,
  "available": true,               // false => data missing, NEVER fabricated
  "provenance": ["binance_ws", "coingecko"],
  "methodology_version": "pressure.v1",  // where applicable, else null
  "data": { … }
}
```

Errors: `{ "error": { "code": "unauthorized|forbidden|rate_limited|not_found|bad_request|upstream_unavailable", "message": str, "request_id": str } }`
with matching HTTP status. `available:false` is HTTP 200; `not_found` is 404.

Pagination (news, events): cursor-based. `?limit=50&cursor=<opaque>` →
`data.items`, `data.next_cursor` (null when exhausted). Cursors are opaque
URL-safe strings encoding the last item's (timestamp, id).

## REST endpoints (relative to /api/v1/agent)

- `GET /market/overview` — data: `{ total_market_cap, total_volume_24h, btc_dominance, eth_dominance, market_cap_change_24h_pct, fear_greed: {value, classification, source, attribution}|null }`
- `GET /assets/{asset}/snapshot?venue=&instrument=` — compact composite: price per venue/instrument, 1h/24h/7d change, taker ratio, book imbalance, funding, OI, basis, trend. `venue` = `binance|bybit` (omit = all), `instrument` = `spot|usdt_perp` (omit = all). Asset is a base ticker (`BTC`).
- `GET /assets/{asset}/news?limit=&cursor=&category=&kind=` — items: contract `NewsItem` shape.
- `GET /news?limit=&cursor=&category=&kind=` — global news feed (same shape, all assets).
- `GET /assets/{asset}/pressure?timeframe=1h` — data: contract `PressureReport` plus `volume_acceleration` (ratio of recent-window taker volume to prior window, null when unavailable).
- `GET /assets/{asset}/derivatives` — data: contract `DerivativesReport` plus `oi_change_pct_1h`, `funding_change_1h`, `perp_premium_pct`.
- `GET /assets/{asset}/liquidity` — data: contract `LiquidityReport`; zones keep `type` ∈ `observed_bid_wall|observed_ask_wall|estimated_liquidation|estimated_support|estimated_resistance` and `label` prefix `ESTIMATED` for model outputs. Adds `sweeps: [{time, direction, price, source}]` (detected, may be []).
- `GET /assets/{asset}/sentiment` — data: contract sentiment report (proprietary; disclaimer included verbatim).
- `GET /assets/{asset}/scenarios` — data: `{ scenarios: ScenarioV2[], market_state: dict }`.
- `GET /assets/{asset}/cross-exchange` — data: `{ pairs: [{ venues: ["binance","bybit"], instrument, price_a, price_b, spread_bps, funding_gap, oi_gap_pct, agreeing: bool|null }], btc_eth: { correlation_note: str, btc_change_24h, eth_change_24h, diverging: bool }|null, spot_vs_perp: {...}|null }`
- `GET /events?limit=&cursor=&type=&asset=&severity=&since=` — durable event history (newest first), same envelope; `data.items: AgentEvent[]`, `data.next_cursor`.
- `GET /system/health` — data: `{ status, services: {redis, database, binance_ws, bybit_ws, coingecko}, event_stream: {backend: "redis_streams"|"memory", depth: int}, uptime_sec }`

## ScenarioV2 (superset of the dashboard scenario shape — same engine output)

```json
{
  "id": "str", "type": "bullish_continuation|bearish_continuation|bullish_reversal|bearish_reversal|short_squeeze|long_squeeze|range_continuation|no_trade|bullish_breakout|bearish_sweep",
  "asset": "BTC", "instrument": "usdt_perp",
  "title": "str", "bias": "long|short|none", "market_regime": "trending_up|trending_down|ranging|unknown",
  "status": "active|invalidated|expired",
  "trigger_conditions": [], "confirmation_signals": [], "invalidation_conditions": [],
  "evidence": [{ "indicator": "str", "value": "str", "supports": true }],
  "contradicting_evidence": [{ "indicator": "str", "value": "str" }],
  "target_zones": [{ "price_low": 0, "price_high": 0, "label": "str" }],
  "risks": [], "confidence": 0.0, "confidence_note": "rule-vote fraction, NOT a calibrated probability",
  "methodology": "str", "methodology_version": "scenarios.v2",
  "generated_at": "ISO", "stale": false
}
```

Legacy fields (`trigger_conditions`, `confirmation_signals`, `target_zones`, `risks`,
`evidence`, `confidence`, `generated_at`, `stale`) keep their exact names so the
existing dashboard keeps working unchanged.

## Event stream

WebSocket: `GET /api/v1/agent/stream` (upgrade). Auth via `X-API-Key` header or
`?api_key=` (header preferred). Scope `stream` required.

Client → server (first message, JSON):
```json
{ "action": "subscribe", "assets": ["BTC","ETH"], "venues": ["binance"], "event_types": ["FUNDING_EXTREME"], "severities": ["warning","critical"], "last_event_id": "169…-0" }
```
`last_event_id` (optional) triggers replay of missed durable events before live
streaming (gap recovery). All filters optional; omit = receive all.

Server → client messages:
```json
{ "kind": "subscribed", "subscription_id": "str", "replay_from": "…|null" }
{ "kind": "event", "event": AgentEvent }
{ "kind": "heartbeat", "ts": 1234567890.0 }
```

Durability: events are appended to a Redis Stream (`skybus:events`, MAXLEN ~10k,
approximate trimming) — NOT pub/sub. Replay uses `XREVRANGE`/`XRANGE` from
`last_event_id`. When Redis is unavailable, an in-process ring buffer (5k) is
used and `event_stream.backend` reports `"memory"` — replay then covers only
process lifetime, and consumers can detect this via `/system/health`.
Ordering: stream IDs (time-ordered) per server; idempotency via `idempotency_key`
(also the dedupe key consumers should keep for ≥24h).

Cursor direction semantics (important):

- **WS `last_event_id`** = gap recovery: replays events *newer than* the id
  (exclusive), oldest-first, then continues live. No duplicates, no silent gaps.
- **REST `GET /events?cursor=`** = backwards pagination: `cursor` is the
  `stream_id` of the last item of the previous page; the next page contains
  *older* events, newest-first.

Auth failures on the WS close the socket with close code **4401** (the server
accepts first so the code survives; missing/invalid key or missing `stream`
scope both yield 4401).

### AgentEvent (CloudEvents-inspired)

```json
{
  "specversion": "1.0",
  "id": "01J…",                      // ULID, unique
  "type": "PRICE_LEVEL_CROSSED",     // enum below
  "source": "skybus://detectors/funding",
  "time": "ISO",                     // event time
  "published_at": "ISO",
  "asset": "BTC|null", "venue": "binance|null", "instrument": "usdt_perp|null",
  "severity": "info|warning|critical",
  "confidence": 0.0,                 // null when not applicable
  "summary": "human-readable one-liner",
  "evidence": [{ "indicator": "str", "value": "str", "supports": true }],
  "measurements": { "observed": { … }, "estimated": { … } },
  "methodology_version": "detectors.v1",
  "idempotency_key": "funding:BTC:2026-10-23T16:00",
  "scenario_id": null,
  "stream_id": "1698150000000-0"     // set when persisted to the stream
}
```

`measurements.observed` = directly observed exchange data;
`measurements.estimated` = model outputs, always separately labelled.

Event types (enum): `PRICE_LEVEL_CROSSED, LIQUIDITY_ZONE_APPROACH,
LIQUIDITY_ZONE_BREACHED, LIQUIDITY_SWEEP_DETECTED, CVD_DIVERGENCE,
OPEN_INTEREST_SPIKE, FUNDING_EXTREME, LONG_LIQUIDATION_BURST,
SHORT_LIQUIDATION_BURST, CROSS_EXCHANGE_DIVERGENCE, NEWS_BREAKING,
MARKET_REGIME_CHANGED, SCENARIO_CREATED, SCENARIO_INVALIDATED, DATA_STALE,
DATA_RECOVERED`.

Detectors run in the backend worker loop against the shared LiveState and
poller outputs; they never fabricate — detectors only fire on fresh observed
inputs, except `DATA_STALE`/`DATA_RECOVERED` which report feed health itself.

## skybus-client (Python package, top-level dir `skybus-client/`)

```python
from skybus_client import SkybusClient
async with SkybusClient(base_url="http://localhost:8123", api_key="…") as c:
    snap = await c.get_snapshot("ETH")
    liq  = await c.get_liquidity("ETH")
    sc   = await c.get_scenarios("ETH")
    async for event in c.stream(assets=["ETH"], last_event_id=last_seen):
        ...  # auto-reconnect w/ exponential backoff, dedupe by idempotency_key
```

Typed pydantic models mirror this document's schemas; `SkybusEvent.stream_id`
is persisted by callers for replay. Exceptions: `SkybusError`,
`SkybusAuthError`, `SkybusRateLimitError`, `SkybusUnavailableError`.

## MCP server (top-level dir `mcp-server/`)

Standalone stdio MCP server (Python `mcp` SDK) exposing read-only tools:
`get_market_overview, get_asset_snapshot, get_latest_news, get_liquidity_zones,
get_derivatives_context, get_market_scenarios, compare_exchange_signals,
explain_market_event`. It calls the agent REST API via `skybus-client` — it
never recalculates indicators, never touches the DB directly, and holds no
credentials beyond the agent API key from its own environment.
