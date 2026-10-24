# SkyBus Backend

FastAPI service implementing the SkyBus API contract (`../docs/API_CONTRACT.md`).

## Layout

```
app/
  main.py             app factory + lifespan (cache, db, workers, event detectors)
  core/               config, cache (Redis w/ in-memory fallback), db, rate limiting,
                      symbol registry, shared live state (WS ticks, depth, trades)
  intelligence/       SHARED facade — the one calculation path used by both the
                      public dashboard routes and the agent API
  agentapi/           machine-consumption namespace /api/v1/agent: auth (API keys,
                      scopes, per-key rate limits, audit), versioned envelopes,
                      request-ID middleware, REST routers, WS event stream
  events/             CloudEvents-inspired event model, durable bus (Redis Streams
                      w/ in-memory fallback), 16 detectors, replay
  models/             SQLAlchemy schema (TimescaleDB hypertables for time series)
  schemas/            pydantic request/response docs models
  services/           upstream clients: coingecko, binance (REST+WS), bybit (REST+WS),
                      alternative.me fear&greed, dexscreener, defillama, coinglass
                      (optional premium), news/ (newsdata, gnews, rss + aggregator)
  engines/            pressure (taker flow/CVD/imbalance/volume acceleration),
                      liquidity (walls, sweeps, withdrawals, heatmap, labelled
                      estimated liquidation clusters), scenarios v1 (dashboard) +
                      scenarios_v2 (8 types, regime, contradicting evidence),
                      crossproduct (venue comparison, BTC/ETH divergence),
                      contract_norm (linear/inverse normalization),
                      sentiment (proprietary composite), categorizer (news)
  workers/            ingestor (WS supervisors), pollers (market/news/derivatives),
                      alerts (rule evaluator w/ cooldowns + dedupe)
  api/routers/        market, coins (thin wrappers over intelligence/), news,
                      alerts, system (/health, /ws)
alembic/              migrations (0001 schema + hypertables; 0002 agent_audit)
tests/                offline pytest suite (engines, events, detectors, agent API)
```

## Agent API & event stream

Machine consumers (GT Quant) use the authenticated namespace `/api/v1/agent/`
(API keys via `AGENT_API_KEYS` in `.env`) and the durable event stream
`/api/v1/agent/stream` (Redis Streams + replay). The full contract is in
`../docs/AGENT_CONTRACT.md`; integration guide in `../docs/GTQUANT_INTEGRATION.md`.

## Run

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# docs: http://localhost:8000/docs
```

Everything optional degrades gracefully: no Redis → in-memory cache; no Postgres →
no persistence; no news/CoinGlass keys → those sources report `configured: false` /
`available: false`. Unavailable data is reported, never fabricated.

## Tests

```bash
pip install -r requirements-dev.txt
pytest            # fully offline; upstreams are monkeypatched
```

## Migrations

```bash
DATABASE_URL=postgresql+asyncpg://skybus:...@localhost:5432/skybus alembic upgrade head
```

TimescaleDB hypertables are created best-effort; plain PostgreSQL also works.

## Notes

- Rate limits: per-host token bucket + aggressive caching (CoinGecko free tier).
- All upstream payloads carry `fetched_at`; expired cache served with `stale: true`.
- The WS endpoint `/api/v1/ws` fans out live ticks and alert events; clients may also poll.
