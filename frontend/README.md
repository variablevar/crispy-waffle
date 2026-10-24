# SkyBus Frontend

Professional dark-mode crypto news & trading intelligence terminal.
Next.js 15 (App Router) · TypeScript (strict) · Tailwind CSS v3.4 · lightweight-charts v4 · lucide-react.

## Backend connection

The UI talks to the FastAPI backend through a Next.js rewrite proxy:
`/api/:path*` → `${BACKEND_INTERNAL_URL || http://localhost:8000}/api/:path*`
(see `next.config.js`). API shapes follow `../docs/API_CONTRACT.md` — types live in `lib/api.ts`.

## Develop

```bash
npm install
BACKEND_INTERNAL_URL=http://localhost:8000 npm run dev
# open http://localhost:3000
```

## Build & run

```bash
npm run build
npm start   # port 3000
```

## Docker

```bash
docker build -t skybus-frontend .
docker run -p 3000:3000 -e BACKEND_INTERNAL_URL=http://backend:8000 skybus-frontend
```

## Structure

- `app/` — pages: dashboard (`/`), coin intel (`/crypto/[symbol]`), news (`/news`), alerts (`/alerts`), defi (`/defi`), agent events (`/events`)
- `components/ui/` — hand-written shadcn-style primitives (button, card, badge, tabs, table, skeleton, input, select, dialog, tooltip, scroll-area)
- `components/coin/` — per-tab panels of the coin page (overview, chart, indicators, pressure, derivatives, liquidity, scenarios, alerts, news)
- `components/event-card.tsx`, `components/events-feed.tsx`, `components/agent-activity-panel.tsx` — agent event intelligence UI (observed vs ESTIMATED measurement blocks, severity badges, evidence lists)
- `lib/api.ts` — typed API client (one fetcher per endpoint)
- `lib/agent-api.ts` — SERVER-SIDE ONLY fetcher for `/api/v1/agent/events` using `AGENT_API_KEY` from the server environment (never shipped to the browser; client components poll the route handler `app/api/agent-events/route.ts` instead)
- `lib/use-polling.ts` — polling hook (live panels ≥5s, tables ≥60s)
- `lib/indicators.ts` — client-side TA (SMA/EMA/RSI/MACD/Bollinger) computed from chart candles
- `lib/format.ts` — compact USD / percent / relative-time formatting

Every data panel implements loading skeletons, error states with retry, empty states,
and stale/unavailable badges driven by the contract's `stale` / `available` fields.
The agent events feed additionally has explicit not-configured and unauthorized
states (set `AGENT_API_KEY` on the frontend server to enable it).
