"""Typed pydantic models mirroring docs/AGENT_CONTRACT.md (agent.v1).

All models tolerate unknown extra fields (``extra="allow"``) so the client
keeps working when the server adds fields within ``schema_version``
``agent.v1``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Generic, List, Literal, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "Envelope",
    "FearGreed",
    "MarketOverview",
    "SnapshotPrice",
    "AssetSnapshot",
    "NewsItem",
    "NewsPage",
    "CvdPoint",
    "SpotVsFutures",
    "TimeframePressure",
    "PressureReport",
    "FundingHistoryPoint",
    "FundingInfo",
    "OiHistoryPoint",
    "OpenInterestInfo",
    "LongShortRatio",
    "Liquidation",
    "LiquidationInfo",
    "DerivativesReport",
    "ZoneType",
    "LiquidityZone",
    "OrderbookWall",
    "OrderbookWalls",
    "LiquidityHeatmap",
    "LiquiditySweep",
    "LiquidityReport",
    "SentimentComponents",
    "SentimentReport",
    "Evidence",
    "ContradictingEvidence",
    "TargetZone",
    "Scenario",
    "ScenarioSet",
    "CrossExchangePair",
    "BtcEthCorrelation",
    "CrossExchangeReport",
    "EventType",
    "EventEvidence",
    "EventMeasurements",
    "AgentEvent",
    "ServiceStatus",
    "EventStreamStatus",
    "SystemHealth",
    "EventsPage",
]

T = TypeVar("T")

ZoneType = Literal[
    "observed_bid_wall",
    "observed_ask_wall",
    "estimated_liquidation",
    "estimated_support",
    "estimated_resistance",
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class _Model(BaseModel):
    model_config = ConfigDict(extra="allow")


class Envelope(_Model, Generic[T]):
    """Versioned agent.v1 response envelope.

    ``data`` is ``None`` when ``available`` is false (the server never
    fabricates missing data; it returns HTTP 200 with ``available: false``).
    """

    schema_version: str
    request_id: Optional[str] = None
    observed_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    freshness_sec: Optional[float] = None
    stale: bool = False
    available: bool = True
    provenance: List[str] = Field(default_factory=list)
    methodology_version: Optional[str] = None
    data: Optional[T] = None

    def is_fresh(self, max_age_sec: float) -> bool:
        """True when the observation is at most ``max_age_sec`` old.

        Uses ``observed_at`` (the underlying observation time), falling back
        to ``processed_at``. A server-asserted ``stale: true`` always counts
        as not fresh. Timestamps without a timezone are assumed UTC.
        """
        if self.stale:
            return False
        ts = self.observed_at or self.processed_at
        if ts is None:
            return True
        age = (_utcnow() - _as_utc(ts)).total_seconds()
        return age <= max_age_sec


# ---------------------------------------------------------------------------
# Market overview


class FearGreed(_Model):
    value: float
    classification: str
    source: Optional[str] = None
    attribution: Optional[str] = None


class MarketOverview(_Model):
    total_market_cap: Optional[float] = None
    total_volume_24h: Optional[float] = None
    btc_dominance: Optional[float] = None
    eth_dominance: Optional[float] = None
    market_cap_change_24h_pct: Optional[float] = None
    fear_greed: Optional[FearGreed] = None


# ---------------------------------------------------------------------------
# Asset snapshot


class SnapshotPrice(_Model):
    """Price/change entry for one (venue, instrument) pair."""

    venue: Optional[str] = None
    instrument: Optional[str] = None
    symbol: Optional[str] = None
    price: Optional[float] = None
    change_1h: Optional[float] = None
    change_24h: Optional[float] = None
    change_7d: Optional[float] = None
    funding_rate: Optional[float] = None
    open_interest: Optional[float] = None


class AssetSnapshot(_Model):
    """Compact composite per asset: prices per venue/instrument plus
    aggregate pressure/derivatives signals."""

    asset: Optional[str] = None
    symbol: Optional[str] = None
    prices: List[SnapshotPrice] = Field(default_factory=list)
    change_1h: Optional[float] = None
    change_24h: Optional[float] = None
    change_7d: Optional[float] = None
    taker_ratio: Optional[float] = None
    book_imbalance: Optional[float] = None
    funding: Dict[str, Optional[float]] = Field(default_factory=dict)
    open_interest: Dict[str, Optional[float]] = Field(default_factory=dict)
    basis: Optional[float] = None
    trend: Optional[str] = None
    updated_at: Optional[datetime] = None
    stale: bool = False


# ---------------------------------------------------------------------------
# News


class NewsItem(_Model):
    id: str
    headline: str
    source: str
    source_url: Optional[str] = None
    published_at: datetime
    assets: List[str] = Field(default_factory=list)
    category: Optional[str] = None
    sentiment: Optional[float] = None
    importance: Optional[int] = None
    kind: Optional[str] = None
    summary: Optional[str] = None


class NewsPage(_Model):
    items: List[NewsItem] = Field(default_factory=list)
    next_cursor: Optional[str] = None


# ---------------------------------------------------------------------------
# Pressure


class CvdPoint(_Model):
    time: float
    value: float


class SpotVsFutures(_Model):
    spot_ratio: Optional[float] = None
    futures_ratio: Optional[float] = None


class TimeframePressure(_Model):
    buy: Optional[float] = None
    sell: Optional[float] = None
    ratio: Optional[float] = None


class PressureReport(_Model):
    symbol: str
    taker_buy_volume: Optional[float] = None
    taker_sell_volume: Optional[float] = None
    taker_ratio: Optional[float] = None
    cvd: List[CvdPoint] = Field(default_factory=list)
    book_imbalance: Optional[float] = None
    spot_vs_futures: SpotVsFutures = Field(default_factory=SpotVsFutures)
    timeframes: Dict[str, TimeframePressure] = Field(default_factory=dict)
    methodology: Optional[str] = None
    confidence: Optional[str] = None
    volume_acceleration: Optional[float] = None
    updated_at: Optional[datetime] = None
    stale: bool = False


# ---------------------------------------------------------------------------
# Derivatives


class FundingHistoryPoint(_Model):
    time: float
    exchange: Optional[str] = None
    value: float


class FundingInfo(_Model):
    binance: Optional[float] = None
    bybit: Optional[float] = None
    history: List[FundingHistoryPoint] = Field(default_factory=list)


class OiHistoryPoint(_Model):
    time: float
    value: float


class OpenInterestInfo(_Model):
    binance: Optional[float] = None
    bybit: Optional[float] = None
    history: List[OiHistoryPoint] = Field(default_factory=list)


class LongShortRatio(_Model):
    binance: Optional[float] = None
    bybit: Optional[float] = None


class Liquidation(_Model):
    time: float
    side: str
    size_usd: float
    exchange: Optional[str] = None


class LiquidationInfo(_Model):
    available: bool = False
    source: Optional[str] = None
    note: Optional[str] = None
    recent: List[Liquidation] = Field(default_factory=list)


class DerivativesReport(_Model):
    symbol: str
    funding: FundingInfo = Field(default_factory=FundingInfo)
    open_interest: OpenInterestInfo = Field(default_factory=OpenInterestInfo)
    long_short_ratio: Optional[LongShortRatio] = None
    basis: Optional[float] = None
    liquidations: LiquidationInfo = Field(default_factory=LiquidationInfo)
    oi_change_pct_1h: Optional[float] = None
    funding_change_1h: Optional[float] = None
    perp_premium_pct: Optional[float] = None
    updated_at: Optional[datetime] = None
    stale: bool = False


# ---------------------------------------------------------------------------
# Liquidity


class LiquidityZone(_Model):
    price_low: float
    price_high: float
    type: ZoneType
    strength: float
    size_usd: Optional[float] = None
    exchange: Optional[str] = None  # None = aggregated/model
    label: str = ""  # model outputs carry an "ESTIMATED" prefix
    source: Optional[str] = None

    @property
    def is_estimated(self) -> bool:
        """True for model outputs (``estimated_*`` zone types)."""
        return self.type.startswith("estimated_")


class OrderbookWall(_Model):
    price: float
    size_usd: float
    exchange: Optional[str] = None


class OrderbookWalls(_Model):
    bids: List[OrderbookWall] = Field(default_factory=list)
    asks: List[OrderbookWall] = Field(default_factory=list)


class LiquidityHeatmap(_Model):
    price_points: List[float] = Field(default_factory=list)
    time_points: List[float] = Field(default_factory=list)
    intensity: List[List[float]] = Field(default_factory=list)


class LiquiditySweep(_Model):
    time: float
    direction: str
    price: float
    source: Optional[str] = None


class LiquidityReport(_Model):
    symbol: str
    mid_price: Optional[float] = None
    walls: OrderbookWalls = Field(default_factory=OrderbookWalls)
    zones: List[LiquidityZone] = Field(default_factory=list)
    heatmap: Optional[LiquidityHeatmap] = None
    imbalance: Optional[float] = None
    sweeps: List[LiquiditySweep] = Field(default_factory=list)
    disclaimer: str = ""
    updated_at: Optional[datetime] = None
    stale: bool = False


# ---------------------------------------------------------------------------
# Sentiment


class SentimentComponents(_Model):
    news: Optional[float] = None
    momentum: Optional[float] = None
    volume: Optional[float] = None
    funding: Optional[float] = None


class SentimentReport(_Model):
    asset_score: Optional[float] = None
    label: str = ""
    components: SentimentComponents = Field(default_factory=SentimentComponents)
    market_fear_greed: Optional[FearGreed] = None
    disclaimer: str = ""
    updated_at: Optional[datetime] = None
    stale: bool = False


# ---------------------------------------------------------------------------
# Scenarios (ScenarioV2)


class Evidence(_Model):
    indicator: str
    value: str
    supports: bool


class ContradictingEvidence(_Model):
    indicator: str
    value: str


class TargetZone(_Model):
    price_low: float
    price_high: float
    label: str = ""


class Scenario(_Model):
    """ScenarioV2 — superset of the dashboard scenario shape."""

    id: str
    type: str
    asset: str
    instrument: Optional[str] = None
    title: str = ""
    bias: Literal["long", "short", "none"] = "none"
    market_regime: Literal["trending_up", "trending_down", "ranging", "unknown"] = "unknown"
    status: Literal["active", "invalidated", "expired"] = "active"
    trigger_conditions: List[str] = Field(default_factory=list)
    confirmation_signals: List[str] = Field(default_factory=list)
    invalidation_conditions: List[str] = Field(default_factory=list)
    evidence: List[Evidence] = Field(default_factory=list)
    contradicting_evidence: List[ContradictingEvidence] = Field(default_factory=list)
    target_zones: List[TargetZone] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    confidence: float = 0.0
    confidence_note: Optional[str] = None
    methodology: Optional[str] = None
    methodology_version: Optional[str] = None
    generated_at: Optional[datetime] = None
    stale: bool = False


class ScenarioSet(_Model):
    scenarios: List[Scenario] = Field(default_factory=list)
    market_state: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Cross-exchange


class CrossExchangePair(_Model):
    venues: List[str] = Field(default_factory=list)
    instrument: Optional[str] = None
    price_a: Optional[float] = None
    price_b: Optional[float] = None
    spread_bps: Optional[float] = None
    funding_gap: Optional[float] = None
    oi_gap_pct: Optional[float] = None
    agreeing: Optional[bool] = None


class BtcEthCorrelation(_Model):
    correlation_note: str = ""
    btc_change_24h: Optional[float] = None
    eth_change_24h: Optional[float] = None
    diverging: bool = False


class CrossExchangeReport(_Model):
    pairs: List[CrossExchangePair] = Field(default_factory=list)
    btc_eth: Optional[BtcEthCorrelation] = None
    spot_vs_perp: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Events


class EventType(str, Enum):
    PRICE_LEVEL_CROSSED = "PRICE_LEVEL_CROSSED"
    LIQUIDITY_ZONE_APPROACH = "LIQUIDITY_ZONE_APPROACH"
    LIQUIDITY_ZONE_BREACHED = "LIQUIDITY_ZONE_BREACHED"
    LIQUIDITY_SWEEP_DETECTED = "LIQUIDITY_SWEEP_DETECTED"
    CVD_DIVERGENCE = "CVD_DIVERGENCE"
    OPEN_INTEREST_SPIKE = "OPEN_INTEREST_SPIKE"
    FUNDING_EXTREME = "FUNDING_EXTREME"
    LONG_LIQUIDATION_BURST = "LONG_LIQUIDATION_BURST"
    SHORT_LIQUIDATION_BURST = "SHORT_LIQUIDATION_BURST"
    CROSS_EXCHANGE_DIVERGENCE = "CROSS_EXCHANGE_DIVERGENCE"
    NEWS_BREAKING = "NEWS_BREAKING"
    MARKET_REGIME_CHANGED = "MARKET_REGIME_CHANGED"
    SCENARIO_CREATED = "SCENARIO_CREATED"
    SCENARIO_INVALIDATED = "SCENARIO_INVALIDATED"
    DATA_STALE = "DATA_STALE"
    DATA_RECOVERED = "DATA_RECOVERED"


class EventEvidence(_Model):
    indicator: str
    value: str
    supports: Optional[bool] = None


class EventMeasurements(_Model):
    observed: Dict[str, Any] = Field(default_factory=dict)
    estimated: Dict[str, Any] = Field(default_factory=dict)


class AgentEvent(_Model):
    """CloudEvents-inspired event. ``stream_id`` is set once the event has
    been persisted to the server stream; persist it client-side to resume
    with gap recovery after restarts."""

    specversion: str = "1.0"
    id: str
    type: str  # see EventType; kept as str so unknown new types still parse
    source: Optional[str] = None
    time: Optional[datetime] = None
    published_at: Optional[datetime] = None
    asset: Optional[str] = None
    venue: Optional[str] = None
    instrument: Optional[str] = None
    severity: str = "info"
    confidence: Optional[float] = None
    summary: str = ""
    evidence: List[EventEvidence] = Field(default_factory=list)
    measurements: EventMeasurements = Field(default_factory=EventMeasurements)
    methodology_version: Optional[str] = None
    idempotency_key: Optional[str] = None
    scenario_id: Optional[str] = None
    stream_id: Optional[str] = None


class EventsPage(_Model):
    items: List[AgentEvent] = Field(default_factory=list)
    next_cursor: Optional[str] = None


# ---------------------------------------------------------------------------
# System health


class ServiceStatus(_Model):
    redis: bool = False
    database: bool = False
    binance_ws: bool = False
    bybit_ws: bool = False
    coingecko: bool = False


class EventStreamStatus(_Model):
    backend: str = "memory"  # "redis_streams" | "memory"
    depth: int = 0


class SystemHealth(_Model):
    status: str = "ok"
    services: ServiceStatus = Field(default_factory=ServiceStatus)
    event_stream: EventStreamStatus = Field(default_factory=EventStreamStatus)
    uptime_sec: float = 0.0
