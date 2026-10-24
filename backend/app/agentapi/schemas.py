"""Typed schemas for the agent API (contract: docs/AGENT_CONTRACT.md)."""

from __future__ import annotations

from typing import Any, Generic, List, Optional, TypeVar

from pydantic import BaseModel

SCHEMA_VERSION = "agent.v1"

T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):
    schema_version: str = SCHEMA_VERSION
    request_id: str = ""
    observed_at: Optional[str] = None
    processed_at: str
    freshness_sec: Optional[float] = None
    stale: bool = False
    available: bool = True
    provenance: List[str] = []
    methodology_version: Optional[str] = None
    data: T


class MarketOverviewData(BaseModel):
    total_market_cap: Optional[float] = None
    total_volume_24h: Optional[float] = None
    btc_dominance: Optional[float] = None
    eth_dominance: Optional[float] = None
    market_cap_change_24h_pct: Optional[float] = None
    fear_greed: Optional[dict[str, Any]] = None


class SnapshotPrice(BaseModel):
    venue: str
    instrument: str
    symbol: str
    price: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    spread_bps: Optional[float] = None
    volume_24h: Optional[float] = None
    funding_rate: Optional[float] = None
    open_interest: Optional[float] = None
    stale: bool = False


class SnapshotData(BaseModel):
    asset: str
    prices: List[SnapshotPrice] = []
    trend: str = "neutral"
    change_1h: Optional[float] = None
    change_24h: Optional[float] = None
    change_7d: Optional[float] = None
    taker_ratio: Optional[float] = None
    book_imbalance: Optional[float] = None
    basis: Optional[float] = None
    funding: dict[str, Optional[float]] = {}
    open_interest: dict[str, Optional[float]] = {}


class Page(BaseModel):
    items: List[dict[str, Any]] = []
    next_cursor: Optional[str] = None
