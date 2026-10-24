from skybus_mcp.server import mcp

EXPECTED_TOOLS = {
    "get_market_overview",
    "get_asset_snapshot",
    "get_latest_news",
    "get_liquidity_zones",
    "get_derivatives_context",
    "get_market_scenarios",
    "compare_exchange_signals",
    "explain_market_event",
}


async def test_registry_lists_exactly_the_eight_tools():
    listed = await mcp.list_tools()
    names = {t.name for t in listed}
    assert names == EXPECTED_TOOLS
    assert len(listed) == 8


async def test_tools_have_typed_input_schemas_and_descriptions():
    listed = {t.name: t for t in await mcp.list_tools()}
    snap = listed["get_asset_snapshot"]
    assert "asset" in snap.inputSchema["properties"]
    assert snap.inputSchema["properties"]["asset"]["type"] == "string"
    news = listed["get_latest_news"]
    assert news.inputSchema["properties"]["limit"]["type"] == "integer"
    explain = listed["explain_market_event"]
    assert set(explain.inputSchema["required"]) == {"asset", "question"}
    for tool in listed.values():
        assert tool.description and len(tool.description) > 20


async def test_liquidity_tool_description_flags_estimated_zones():
    listed = {t.name: t for t in await mcp.list_tools()}
    desc = listed["get_liquidity_zones"].description
    assert "ESTIMATED" in desc
    assert "model output" in desc
    assert "not observed" in desc.lower().replace("not observed orders", "not observed")
