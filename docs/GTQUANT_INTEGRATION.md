# GT Quant ↔ SkyBus Integration Guide

SkyBus is the shared market-intelligence infrastructure; GT Quant is an
independent consumer and decision-making system. SkyBus never places orders and
never touches GT Quant's accounts or containers.

## 1. Credentials

Agent access uses API keys configured on the SkyBus backend (`.env`):

```
AGENT_API_KEYS=gtquant:<generate-a-long-random-key>
```

Keys grant the scopes `read` (REST) and `stream` (WebSocket). Restart the
backend after changing keys. Keys are never logged or returned by any endpoint.
Send the key as the `X-API-Key` header (the WS stream also accepts `?api_key=`
for clients that cannot set headers).

## 2. Network connectivity

Same machine, different Docker project (the common case):

- SkyBus backend is published on host port `8123` (this deployment; default
  `8000` on a clean machine). From GT Quant containers use
  `http://host.docker.internal:8123` (add `extra_hosts: ["host.docker.internal:host-gateway"]`
  on Linux) or from the host directly `http://localhost:8123`.
- Alternatively attach a GT Quant container to the SkyBus network:
  `docker network connect skybus_default <gtquant-container>` and use
  `http://backend:8000`. SkyBus does not modify GT Quant's containers — either
  option is initiated from the GT Quant side.
- Remote deployments: put the backend behind TLS (reverse proxy) and use
  `https://` / `wss://` URLs. The API key is a bearer secret — do not use it
  over plaintext across untrusted networks.

## 3. REST quickstart (any HTTP client)

```bash
curl -H "X-API-Key: $SKYBUS_API_KEY" http://localhost:8123/api/v1/agent/assets/ETH/snapshot
curl -H "X-API-Key: $SKYBUS_API_KEY" "http://localhost:8123/api/v1/agent/events?limit=20"
```

Every response is the `agent.v1` envelope: schema version, request id,
observed/processed timestamps, freshness, staleness, provenance, methodology
version, and `data`. `available:false` means the source is down — treat the
data as absent, never as zero.

## 4. Python client quickstart

```bash
pip install -e /path/to/skybus/skybus-client
```

```python
import asyncio, os
from skybus_client import SkybusClient

async def main():
    async with SkybusClient(
        base_url=os.environ["SKYBUS_URL"],       # e.g. http://localhost:8123
        api_key=os.environ["SKYBUS_API_KEY"],
    ) as skybus:
        snapshot  = await skybus.get_snapshot("ETH")
        liquidity = await skybus.get_liquidity("ETH")
        scenarios = await skybus.get_scenarios("ETH")

asyncio.run(main())
```

## 5. Streaming with replay (no silent gaps)

```python
async def consume():
    last_id = load_last_stream_id()          # persisted by GT Quant
    async with SkybusClient(base_url=..., api_key=...) as skybus:
        async for event in skybus.stream(assets=["BTC", "ETH"], last_event_id=last_id):
            handle(event)                     # dedupe by event.idempotency_key
            save_last_stream_id(event.stream_id)
```

- Events are persisted server-side in a Redis Stream (`skybus:events`, ~10k
  retained). Reconnecting with `last_event_id` replays what was missed, then
  continues live. The client reconnects with exponential backoff automatically.
- If SkyBus runs without Redis, the bus degrades to an in-process ring buffer;
  check `GET /api/v1/agent/system/health` → `event_stream.backend`
  (`redis_streams` = durable across restarts, `memory` = process lifetime).
- Dedupe on `idempotency_key` (stable per condition+time-bucket) or `id`.
- Events carry `measurements.observed` (exchange data) and
  `measurements.estimated` (model output) separately — never treat estimated
  liquidation zones as observed orders.

## 6. What SkyBus deliberately does not do

- No order placement, no account management, no write access for agent keys.
- Scenarios are explainable rule evaluations with `confidence_note:
  "rule-vote fraction, NOT a calibrated probability"` — GT Quant is expected
  to disagree when its own models say otherwise.
- No fabricated data: missing feeds produce `available:false`, `DATA_STALE`
  events, and explicit labels.

## 7. MCP server (optional)

`mcp-server/` exposes the same intelligence as MCP tools for LLM agents
(read-only). Configure `SKYBUS_BASE_URL` + `SKYBUS_API_KEY` in its environment;
see `mcp-server/README.md`.

## 8. Error handling

| HTTP | code | meaning |
|------|------|---------|
| 401 | `unauthorized` | missing/invalid API key |
| 403 | `forbidden` | key lacks the required scope |
| 404 | `not_found` | unknown asset |
| 429 | `rate_limited` | per-key bucket exceeded; honor `Retry-After` |
| 200 + `available:false` | — | upstream source down; data absent, not zero |

The Python client maps these to `SkybusAuthError`, `SkybusNotFoundError`,
`SkybusRateLimitError`, `SkybusUnavailableError`.
