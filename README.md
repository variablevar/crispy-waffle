# SkyBus — Crypto News & Trading Intelligence Platform

A real-time cryptocurrency intelligence terminal combining market rankings, derivatives
analytics, news aggregation, liquidity visualization, a rule-based trading-scenario
engine and an alert system — built on genuinely live public data with explicit
data-quality and uncertainty labels.

## Architecture

```
┌────────────────────────────┐        ┌──────────────────────────────────────┐
│  Frontend (Next.js 15)     │  HTTP  │  Backend (FastAPI, Python 3.11+)     │
│  App Router · TS · Tailwind│───────▶│  REST /api/v1 · WebSocket /api/v1/ws │
│  lightweight-charts        │  WS    │                                      │
└────────────────────────────┘        │  services/   exchange & news clients │
                                      │  engines/    pressure · liquidity ·  │
                                      │             scenarios · sentiment    │
                                      │  workers/    WS ingestors · pollers  │
                                      └───────┬───────────────┬──────────────┘
                                              │               │
                                     ┌────────▼───┐   ┌───────▼────────┐
                                     │ Redis 7    │   │ TimescaleDB    │
                                     │ cache/state│   │ (Postgres 16)  │
                                     └────────────┘   └────────────────┘
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
- The scenario engine is rule-based and explainable; it is not financial advice.

## Quick start (Docker)

```bash
cp .env.example .env          # optionally add news/CoinGlass keys
docker compose up --build
# frontend http://localhost:3000   backend http://localhost:8000/docs
```

## Local development (no Docker)

```bash
# Backend (Python 3.11+)
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Redis/Postgres are optional for dev — the backend degrades gracefully
# (in-memory cache, no persistence). To enable them:
docker compose up db redis

# Frontend (Node 20+)
cd frontend && npm install && npm run dev
```

## Tests

```bash
cd backend && pip install -r requirements-dev.txt && pytest
cd frontend && npm run build   # type-checks the whole app
```

## Repo layout

```
backend/    FastAPI app — see backend/README.md
frontend/   Next.js app — see frontend/README.md
docs/       API contract & methodology notes
```

## Phases delivered

1. Dashboard (top 10 by mcap + top 10 non-stablecoin by volume), coin pages, charts, news ingestion.
2. Binance/Bybit websockets, order books, buy/sell pressure engine, funding & OI.
3. Liquidity intelligence (walls, heatmap, labelled estimated liquidation clusters), scenario engine.
4. DeFi liquidity, cross-product analytics, alert system with in-app notifications.
5. Tests, caching, rate-limit handling, deployment readiness.
6. Agent-native layer: authenticated `/api/v1/agent/` REST API (versioned envelopes, request IDs,
   rate limiting, audit), durable Redis-Streams event bus with 16 detectors and WS replay,
   `skybus-client` Python package, read-only MCP server, dashboard agent-event feed.
   See `docs/AGENT_CONTRACT.md` and `docs/GTQUANT_INTEGRATION.md`.
