from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_DIR.parent


class Settings(BaseSettings):
    """Runtime configuration. All values can come from the environment / .env.

    The app must boot and serve with no Redis, no Postgres and no API keys —
    every optional dependency degrades gracefully.
    """

    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT / ".env", _BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    backend_port: int = 8000
    cors_origins: str = "http://localhost:3000"

    database_url: str = "postgresql+asyncpg://skybus:skybus_dev_password@localhost:5432/skybus"
    redis_url: str = "redis://localhost:6379/0"

    coingecko_api_key: str = ""
    coingecko_base_url: str = "https://api.coingecko.com/api/v3"

    newsdata_api_key: str = ""
    gnews_api_key: str = ""
    coinglass_api_key: str = ""

    tracked_symbols: str = "BTC,ETH,SOL,XRP,BNB,DOGE,ADA,TRX,AVAX,LINK"
    market_poll_interval: int = 60
    news_poll_interval: int = 300
    fear_greed_poll_interval: int = 600
    derivatives_poll_interval: int = 45

    # Master switch for background workers / websocket ingestors (tests disable it).
    workers_enabled: bool = True

    # --- Agent API (GT Quant & other machine consumers) ---
    # Comma-separated name:key pairs, e.g. "gtquant:abc123,research:def456".
    # Keys grant scopes read+stream. Empty => agent API disabled (401 for all).
    agent_api_keys: str = ""
    agent_rate_limit_per_min: int = 120
    # Event stream durability
    event_stream_name: str = "skybus:events"
    event_stream_maxlen: int = 10_000
    event_ring_fallback: int = 5_000
    # Detector loop cadence (seconds)
    detector_interval: int = 5

    log_level: str = "INFO"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def tracked_symbol_list(self) -> list[str]:
        return [s.strip().upper() for s in self.tracked_symbols.split(",") if s.strip()]

    @property
    def agent_key_map(self) -> dict[str, str]:
        """{consumer_name: api_key} parsed from agent_api_keys."""
        out: dict[str, str] = {}
        for pair in self.agent_api_keys.split(","):
            pair = pair.strip()
            if ":" in pair:
                name, key = pair.split(":", 1)
                if name.strip() and key.strip():
                    out[name.strip()] = key.strip()
        return out


@lru_cache
def get_settings() -> Settings:
    return Settings()
