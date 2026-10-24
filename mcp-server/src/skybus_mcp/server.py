"""SkyBus MCP server — read-only tools over the SkyBus agent REST API.

Run over stdio:  python -m skybus_mcp
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import tools

INSTRUCTIONS = (
    "SkyBus crypto intelligence (read-only). All data is proxied from the "
    "SkyBus agent REST API — no indicator is recalculated here and no data "
    "is fabricated; when an upstream endpoint is unavailable the tool "
    "reports a structured error or marks the section unavailable. Liquidity "
    "zones labelled ESTIMATED are model outputs, not observed orders. "
    "Scenario confidence is a rule-vote fraction, not a calibrated "
    "probability. These tools cannot execute trades, access databases, or "
    "run shell commands."
)

mcp = FastMCP("skybus-mcp", instructions=INSTRUCTIONS)

for _fn in (
    tools.get_market_overview,
    tools.get_asset_snapshot,
    tools.get_latest_news,
    tools.get_liquidity_zones,
    tools.get_derivatives_context,
    tools.get_market_scenarios,
    tools.compare_exchange_signals,
    tools.explain_market_event,
):
    mcp.tool()(_fn)


def main() -> None:
    mcp.run()  # stdio transport


if __name__ == "__main__":
    main()
