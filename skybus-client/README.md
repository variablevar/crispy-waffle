# skybus-client

Typed async Python client for the **SkyBus** crypto intelligence platform's
agent API (`docs/AGENT_CONTRACT.md`, schema `agent.v1`). Built for machine
consumers such as **GT Quant**; it has no dependency on the SkyBus backend
source tree — only on the published contract.

- Async REST over `httpx` with retries, typed errors and envelope parsing
- WebSocket event stream over `websockets` with auto-reconnect, gap-recovery
  resume and idempotency dedupe
- Pydantic v2 models mirroring the contract schemas (`Envelope[T]`, reports,
  `AgentEvent`, …)

## Install

```bash
# editable, with dev/test extras
pip install -e ".[dev]"

# or straight from the path
pip install /path/to/sky-bus/skybus-client
```

Requires Python ≥ 3.10.

## Quickstart

```python
import asyncio
from skybus_client import SkybusClient

async def main() -> None:
    async with SkybusClient(base_url="http://localhost:8123", api_key="…") as c:
        snap = await c.get_snapshot("ETH")
        liq  = await c.get_liquidity("ETH")
        sc   = await c.get_scenarios("ETH")

        if snap.available:
            print(snap.data.trend, snap.data.taker_ratio)

        last_seen = load_last_event_id()  # your persistence
        async for event in c.stream(assets=["ETH"], last_event_id=last_seen):
            print(event.type, event.severity, event.summary)
            if event.stream_id:
                save_last_event_id(event.stream_id)

asyncio.run(main())
```

Every REST method returns an `Envelope[T]` — the parsed contract envelope
(`schema_version`, `request_id`, `observed_at`, `processed_at`,
`freshness_sec`, `stale`, `available`, `provenance`, `methodology_version`,
`data`). `envelope.data` is `None` when `available` is false: SkyBus never
fabricates missing data, and neither does this client.

### REST surface

| Method | Endpoint (relative to `/api/v1/agent`) |
| --- | --- |
| `get_market_overview()` | `GET /market/overview` |
| `get_snapshot(asset, venue=None, instrument=None)` | `GET /assets/{asset}/snapshot` |
| `get_news(asset=None, limit=50, cursor=None)` / `iter_news(asset)` | `GET /assets/{asset}/news` |
| `get_pressure(asset, timeframe=None)` | `GET /assets/{asset}/pressure` |
| `get_derivatives(asset)` | `GET /assets/{asset}/derivatives` |
| `get_liquidity(asset)` | `GET /assets/{asset}/liquidity` |
| `get_sentiment(asset)` | `GET /assets/{asset}/sentiment` |
| `get_scenarios(asset)` | `GET /assets/{asset}/scenarios` |
| `get_cross_exchange(asset)` | `GET /assets/{asset}/cross-exchange` |
| `get_events(limit, cursor, type, asset, severity, since)` / `iter_events(...)` | `GET /events` |
| `get_health()` | `GET /system/health` |

`iter_news` / `iter_events` follow the opaque `next_cursor` until the server
signals exhaustion (`null`).

### Freshness

Each envelope exposes `is_fresh(max_age_sec)` (based on `observed_at`,
falling back to `processed_at`; server-asserted `stale: true` always counts
as not fresh). To make staleness a hard failure, opt in:

```python
SkybusClient(url, key, max_acceptable_staleness_sec=30)
# stale responses now raise SkybusStaleDataError instead of being returned
```

## GT Quant integration sketch

Credentials come from the environment; `last_event_id` is persisted to disk
so a restart replays missed durable events (gap recovery) instead of losing
them. Check `get_health().data.event_stream.backend` — when it reports
`"memory"` (Redis down), replay only covers the server's process lifetime.

```python
import asyncio, json, os
from pathlib import Path

from skybus_client import SkybusClient, SkybusRateLimitError, SkybusUnavailableError

BASE_URL = os.environ["SKYBUS_BASE_URL"]          # e.g. http://skybus.internal:8123
API_KEY  = os.environ["SKYBUS_API_KEY"]           # key with read + stream scopes
STATE    = Path(os.environ.get("SKYBUS_STATE_FILE", "/var/lib/gtquant/skybus_stream.json"))

def load_last_event_id() -> str | None:
    try:
        return json.loads(STATE.read_text())["last_event_id"]
    except (OSError, ValueError, KeyError):
        return None

def save_last_event_id(stream_id: str) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"last_event_id": stream_id}))
    tmp.replace(STATE)  # atomic

async def snapshot_loop(c: SkybusClient) -> None:
    while True:
        try:
            snap = await c.get_snapshot("BTC")
            if snap.available and snap.is_fresh(30):
                on_snapshot(snap.data)          # feed the strategy
        except SkybusUnavailableError as exc:   # backend down after retries
            log.warning("skybus unavailable: %s", exc)
        await asyncio.sleep(5)

async def event_loop(c: SkybusClient) -> None:
    async for event in c.stream(
        assets=["BTC", "ETH"],
        severities=["warning", "critical"],
        last_event_id=load_last_event_id(),     # replay what we missed
    ):
        on_event(event)                          # dedupe is done client-side
        if event.stream_id:
            save_last_event_id(event.stream_id)  # resume point across restarts

async def main() -> None:
    async with SkybusClient(BASE_URL, API_KEY, max_acceptable_staleness_sec=60) as c:
        await asyncio.gather(snapshot_loop(c), event_loop(c))

asyncio.run(main())
```

The stream reconnects automatically with exponential backoff (0.5 s → 30 s
cap, jittered), resumes from the last received `stream_id`, and drops
duplicates by `idempotency_key` and event `id` (bounded in-memory set). The
contract still advises persisting `idempotency_key`s for ≥24 h if you need
cross-restart dedupe of *processing* (not just of the live stream).

## Error handling

All exceptions subclass `skybus_client.SkybusError` and carry `.status`
(`None` for pure network failures), `.request_id` and the contract error
`.code`.

| Exception | Raised on | Notes |
| --- | --- | --- |
| `SkybusAuthError` | 401 / 403 | bad key, or key lacks the required scope (`read`/`stream`) |
| `SkybusRateLimitError` | 429 | `.retry_after` mirrors the `Retry-After` header; retried internally while retries remain |
| `SkybusNotFoundError` | 404 | e.g. unknown asset |
| `SkybusUnavailableError` | 5xx / network | only after `max_retries` (default 3) retries with backoff |
| `SkybusStaleDataError` | any 2xx | only when `max_acceptable_staleness_sec` is set and the envelope is not fresh |
| `SkybusError` | other 4xx, protocol violations | generic fallback |

Note: `available: false` is **not** an error — it is HTTP 200 with
`envelope.data is None`.

## Development

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
```

Tests are fully offline: HTTP is mocked with `respx`, and the WebSocket
stream logic (frame parsing, dedupe, backoff, reconnect/resume) is exercised
against a fake socket — no real network, no SkyBus backend required.
