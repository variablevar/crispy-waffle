# skybus-mcp

Read-only [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server
that exposes **SkyBus crypto intelligence** as tools for AI agents.

It is a thin proxy: every tool calls the SkyBus **agent REST API**
(`docs/AGENT_CONTRACT.md`, base `/api/v1/agent`, auth via `X-API-Key`).
**No indicator is ever recalculated here**, no database is touched, no shell
commands are run, and no trades can be executed. When upstream data is
missing, tools say so (`available: false`, structured errors) instead of
fabricating.

## Approach

Built on the official Python `mcp` SDK (FastMCP, pinned `mcp>=1.0,<2`; the
2.x line renamed FastMCP to MCPServer). For SkyBus access it prefers the
sibling [`skybus-client`](../skybus-client) package when it is importable
(`from skybus_client import SkybusClient`) and falls back to plain `httpx`
calls against the agent REST endpoints otherwise — so the server works even
before the client package ships.

## Install

```bash
cd mcp-server
python3.11 -m venv .venv
.venv/bin/pip install -e .[dev]      # or: pip install -e .
```

Optional, preferred transport once available:

```bash
.venv/bin/pip install -e ../skybus-client
```

## Configuration

Environment variables (read by the server process, at call time):

| Variable          | Default                 | Meaning                                  |
|-------------------|-------------------------|------------------------------------------|
| `SKYBUS_BASE_URL` | `http://localhost:8123` | SkyBus backend base URL                  |
| `SKYBUS_API_KEY`  | *(none)*                | Agent API key. **Required at call time** — the server starts fine without it, but every tool returns a structured `missing_api_key` error until it is set. |

### Claude Desktop / MCP client config

```json
{
  "mcpServers": {
    "skybus": {
      "command": "/home/gt/Desktop/sky-bus/mcp-server/.venv/bin/python",
      "args": ["-m", "skybus_mcp"],
      "env": {
        "SKYBUS_BASE_URL": "http://localhost:8123",
        "SKYBUS_API_KEY": "your-agent-api-key"
      }
    }
  }
}
```

## Tools (8, all read-only)

| Tool | Description |
|------|-------------|
| `get_market_overview()` | Total market cap, volume, BTC/ETH dominance, 24h change, Fear & Greed index (source + attribution passed through verbatim). |
| `get_asset_snapshot(asset)` | Composite snapshot: price per venue/instrument, 1h/24h/7d change, taker ratio, book imbalance, funding, OI, basis, trend. |
| `get_latest_news(asset=None, limit=20)` | Categorized, deduped news with source/kind/category/sentiment/importance. `limit` clamped to 1–100. |
| `get_liquidity_zones(asset)` | Observed bid/ask walls vs `ESTIMATED` zones. **Estimated zones are model outputs, not observed orders**; labels are preserved verbatim and this caveat is stated in the tool description and response. |
| `get_derivatives_context(asset)` | Funding, OI (+1h changes), basis, perp premium, long/short. Liquidation-data availability is reported by the API, never fabricated. |
| `get_market_scenarios(asset)` | ScenarioV2 list: triggers, confirmations, invalidations, evidence, target zones, confidence + `confidence_note` (rule-vote fraction, not a calibrated probability). |
| `compare_exchange_signals(asset)` | Cross-exchange spreads (bps), funding/OI gaps, venue agreement, BTC/ETH correlation, spot-vs-perp context. |
| `explain_market_event(asset, question)` | Deterministic explainer: fetches snapshot + liquidity + scenarios + recent news from the API and composes a structured textual explanation. No LLM calls, no fabrication; unavailable endpoints are listed under `unavailable`, and ESTIMATED liquidity labels are explicitly marked as model outputs. |

Every response includes the `agent.v1` envelope metadata (`observed_at`,
`freshness_sec`, `stale`, `available`, `provenance`, `request_id`) alongside
`data`, so callers can judge freshness.

## Security notes

- **Read-only.** The server exposes no write, trade, database, or shell
  capability; it only issues authenticated `GET` requests to the agent API.
- **Single credential.** The only secret is `SKYBUS_API_KEY`, read from the
  server's own environment at call time. It is sent as the `X-API-Key`
  header and is never logged, returned, or embedded in tool output.
- **Fail closed.** Missing key → structured `missing_api_key` error (the
  server still starts). HTTP errors map to structured errors
  (`unauthorized`, `forbidden`, `rate_limited`, …) with the API's
  `request_id`; nothing is retried blindly or fabricated.
- **Input hygiene.** Asset tickers are validated (`^[A-Za-z0-9]{2,15}$`,
  uppercased) before being placed in a URL path; limits are clamped.

## Development

```bash
.venv/bin/python -m pytest            # offline tests (respx mocks the HTTP layer)
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | .venv/bin/python -m skybus_mcp
```
