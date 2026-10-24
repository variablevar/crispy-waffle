import httpx
import pytest
import respx

BASE = "http://testserver"
API = BASE + "/api/v1/agent"


@pytest.fixture(autouse=True)
def skybus_env(monkeypatch):
    monkeypatch.setenv("SKYBUS_BASE_URL", BASE)
    monkeypatch.setenv("SKYBUS_API_KEY", "test-key")
    # Ensure the httpx fallback path is exercised even if skybus-client
    # happens to be installed in the environment.
    monkeypatch.setattr("skybus_mcp.client._skybus_client_cls", lambda: None)


def envelope(data, **overrides):
    env = {
        "schema_version": "agent.v1",
        "request_id": "01JTEST",
        "observed_at": "2026-10-23T16:00:00Z",
        "processed_at": "2026-10-23T16:00:04Z",
        "freshness_sec": 4.0,
        "stale": False,
        "available": True,
        "provenance": ["binance_ws"],
        "methodology_version": None,
        "data": data,
    }
    env.update(overrides)
    return env


def mock_get(url, payload, status=200):
    return respx.get(url).mock(return_value=httpx.Response(status, json=payload))
