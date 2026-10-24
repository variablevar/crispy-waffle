# SkyBus — Crypto News & Trading Intelligence Platform

A real-time cryptocurrency intelligence terminal combining market rankings, derivatives
analytics, news aggregation, liquidity visualization, a rule-based trading-scenario
engine and an alert system — built on genuinely live public data with explicit
data-quality and uncertainty labels.

SkyBus serves two kinds of consumers from **one shared intelligence layer**:

1. **Humans** — the Next.js dark-mode terminal (dashboard, coin pages, news, alerts, events).
2. **Machines** — GT Quant and other authorized agents via the authenticated
   `/api/v1/agent/` REST API, the durable WebSocket event stream, the typed
   `skybus-client` Python package, and an optional read-only MCP server.

## Architecture

```
┌────────────────────────────┐        ┌──────────────────────────────────────┐
│  Frontend (Next.js 15)     │  HTTP  │  Backend (FastAPI, Python 3.11+)     │
│  App Router · TS · Tailwind│───────▶│                                      │
│  lightweight-charts        │  WS    │  intelligence/  shared facade — one  │
└────────────────────────────┘        │                 calculation path     │
                                      │  services/      exchange & news      │
┌────────────────────────────┐        │                 clients              │
│  GT Quant / agents         │  REST  │  engines/       pressure · liquidity │
│  skybus-client (Python)    │───────▶│                 · scenarios v2 ·     │
│  /api/v1/agent/*           │  WS    │                 cross-product        │
│  /api/v1/agent/stream      │        │  events/        detectors · Redis-   │
└────────────────────────────┘        │                 Streams bus · replay │
                                      │  agentapi/      auth · envelopes ·   │
┌────────────────────────────┐        │                 stream               │
│  MCP clients (LLM agents)  │  stdio │  workers/       WS ingestors ·       │
│  mcp-server (read-only)    │───────▶│                 pollers · alerts     │
└────────────────────────────┘        └───────┬───────────────┬──────────────┘
                                              │               │
                                     ┌────────▼───┐   ┌───────▼────────┐
                                     │ Redis 7    │   │ TimescaleDB    │
                                     │ cache +    │   │ (Postgres 16)  │
                                     │ event stream│  └────────────────┘
                                     └────────────┘
```

Data sources (all free/public tiers, modular clients):
CoinGecko (market data), Binance + Bybit (public WS/REST: spot & USDT-M perp prices,
klines, aggTrades, depth, funding, OI, long/short ratios, force orders), Alternative.me
(Fear & Greed), DEX Screener + DefiLlama (DeFi liquidity), NewsData.io / GNews / RSS
(news — graceful without keys). CoinGlass is an optional premium integration; without a
key the platform serves a clearly-labelled liquidation **estimation model** instead.

## Principles

- **Never fabricate data.** Unavailable feeds render an explicit "unavailable" state.
- **Every record carries provenance**: source, timestamps, instrument identity, staleness.
- Estimated liquidation levels are labelled as model estimates, never as observed facts.
- The scenario engine is rule-based and explainable; confidence is a rule-vote
  fraction, never a calibrated probability. Nothing here is financial advice.
- SkyBus is intelligence infrastructure only: no order placement, ever.

## Quick start (Docker)

```bash
cp .env.example .env          # add news keys (optional) + AGENT_API_KEYS for agents
docker compose up --build
# frontend http://localhost:3000   backend http://localhost:8000/docs
```

Default ports are 3000/8000/5432; override via `FRONTEND_PORT` / `BACKEND_PORT` /
`DB_PORT` env vars or `.env` when those are taken on your machine.

## Local development (no Docker)

```bash
# Backend (Python 3.11+)
cd backend && python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Redis/Postgres are optional for dev — the backend degrades gracefully
# (in-memory cache, no persistence, in-process event bus). To enable them:
docker compose up db redis

# Frontend (Node 20+)
cd frontend && npm install && npm run dev
```

## Agent access (GT Quant and other consumers)

```bash
# .env
AGENT_API_KEYS=gtquant:<openssl rand -hex 24>
AGENT_API_KEY=<same key>      # lets the dashboard show the agent event feed
```

```python
from skybus_client import SkybusClient   # pip install -e ./skybus-client

async with SkybusClient(base_url="http://localhost:8123", api_key="...") as skybus:
    snapshot  = await skybus.get_snapshot("ETH")
    liquidity = await skybus.get_liquidity("ETH")   # observed vs ESTIMATED zones
    scenarios = await skybus.get_scenarios("ETH")   # trigger/confirm/invalidate
    async for event in skybus.stream(assets=["ETH"], last_event_id=last_seen):
        ...  # durable Redis-Streams replay on reconnect — no silent gaps
```

Docs: `docs/AGENT_CONTRACT.md` (schemas, envelope, events),
`docs/GTQUANT_INTEGRATION.md` (auth, networking, replay semantics).

## MCP server (optional, read-only)

`mcp-server/` exposes the same intelligence as 8 MCP tools
(`get_market_overview`, `get_asset_snapshot`, `get_latest_news`,
`get_liquidity_zones`, `get_derivatives_context`, `get_market_scenarios`,
`compare_exchange_signals`, `explain_market_event`) for LLM agents over stdio.
It proxies the agent REST API — it never recalculates indicators, never touches
the database, and holds only the agent API key. Setup and client config:
`mcp-server/README.md`.

## Tests

```bash
cd backend && pip install -r requirements-dev.txt && pytest    # 82 tests
cd skybus-client && pip install -e ".[dev]" && pytest          # 28 tests
cd mcp-server && pip install -e ".[dev]" && pytest             # 13 tests
cd frontend && npm run build                                   # type-checks the app
```

All test suites are offline-deterministic (upstreams mocked); the engine never
depends on live exchange connections in tests.

## Repo layout

```
backend/        FastAPI app — API, intelligence facade, engines, events, workers
frontend/       Next.js terminal — dashboard, coin pages, news, alerts, events
skybus-client/  Typed async Python client for machine consumers (GT Quant)
mcp-server/     Read-only MCP server over the agent REST API
docs/           API contract, agent contract, methodology, GT Quant integration
```

## Documentation index

| Doc | Contents |
|---|---|
| `docs/API_CONTRACT.md` | Public dashboard API (routes, shapes, enums) |
| `docs/AGENT_CONTRACT.md` | Agent API v1: envelope, endpoints, event schemas, stream protocol |
| `docs/GTQUANT_INTEGRATION.md` | Credentials, Docker networking, replay, error handling |
| `docs/METHODOLOGY.md` | How each indicator is computed; observed vs estimated; limitations |
| `backend/README.md` | Backend layout, migrations, dev notes |
| `frontend/README.md` | Frontend conventions |
| `skybus-client/README.md` | Client install/quickstart, GT Quant sketch |
| `mcp-server/README.md` | MCP tools, config snippet, security notes |

## Phases delivered

1. Dashboard (top 10 by mcap + top 10 non-stablecoin by volume), coin pages, charts, news ingestion.
2. Binance/Bybit websockets, order books, buy/sell pressure engine, funding & OI.
3. Liquidity intelligence (walls, heatmap, labelled estimated liquidation clusters), scenario engine.
4. DeFi liquidity, cross-product analytics, alert system with in-app notifications.
5. Tests, caching, rate-limit handling, deployment readiness.
6. Agent-native layer: authenticated `/api/v1/agent/` REST API (versioned envelopes, request IDs,
   rate limiting, audit), durable Redis-Streams event bus with 16 detectors and WS replay,
   `skybus-client` Python package, read-only MCP server, dashboard agent-event feed.
