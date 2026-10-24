"""SQLAlchemy models — full SkyBus schema.

Every financial record carries its source, timestamp, instrument identity and
can be freshness-checked. Tables are created by the Alembic migration; the app
also works with persistence disabled (workers guard on db.db_available()).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    coingecko_id: Mapped[str | None] = mapped_column(String(80), index=True)
    image: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Exchange(Base):
    __tablename__ = "exchanges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(40), unique=True)


class Instrument(Base):
    __tablename__ = "instruments"
    __table_args__ = (UniqueConstraint("exchange_id", "symbol", "kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exchange_id: Mapped[int] = mapped_column(ForeignKey("exchanges.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(30))          # e.g. BTCUSDT
    kind: Mapped[str] = mapped_column(String(20))            # spot|usdt_perp|inverse_perp|option
    base: Mapped[str] = mapped_column(String(20))
    quote: Mapped[str] = mapped_column(String(20))


class Candle(Base):
    """TimescaleDB hypertable on (time)."""

    __tablename__ = "candles"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), primary_key=True)
    timeframe: Mapped[str] = mapped_column(String(6), primary_key=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(40))


class TradeAgg(Base):
    __tablename__ = "trade_aggs"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), primary_key=True)
    window: Mapped[str] = mapped_column(String(6), primary_key=True)
    taker_buy: Mapped[float] = mapped_column(Float)
    taker_sell: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)


Index("ix_trade_aggs_inst_time", TradeAgg.instrument_id, TradeAgg.time.desc())


class BookSnapshot(Base):
    __tablename__ = "book_snapshots"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), primary_key=True)
    bids: Mapped[dict] = mapped_column(JSONB)
    asks: Mapped[dict] = mapped_column(JSONB)


class FundingHistory(Base):
    __tablename__ = "funding_history"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), primary_key=True)
    rate: Mapped[float] = mapped_column(Float)


class OpenInterestHistory(Base):
    __tablename__ = "open_interest_history"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), primary_key=True)
    value: Mapped[float] = mapped_column(Float)


class Liquidation(Base):
    __tablename__ = "liquidations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    instrument_id: Mapped[int | None] = mapped_column(ForeignKey("instruments.id"))
    side: Mapped[str] = mapped_column(String(8))
    size_usd: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(40))
    estimated: Mapped[bool] = mapped_column(Boolean, default=False)


class NewsArticle(Base):
    __tablename__ = "news_articles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(Text, unique=True)
    headline: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(120))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    sentiment: Mapped[float | None] = mapped_column(Float)
    importance: Mapped[int] = mapped_column(Integer, default=3)
    kind: Mapped[str] = mapped_column(String(16), default="verified")
    summary: Mapped[str | None] = mapped_column(Text)


class NewsAssetLink(Base):
    __tablename__ = "news_assets"

    article_id: Mapped[int] = mapped_column(ForeignKey("news_articles.id"), primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), primary_key=True)


class SentimentMeasurement(Base):
    __tablename__ = "sentiment_measurements"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), primary_key=True)
    score: Mapped[float] = mapped_column(Float)
    components: Mapped[dict] = mapped_column(JSONB)


class LiquidityZone(Base):
    __tablename__ = "liquidity_zones"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    price_low: Mapped[float] = mapped_column(Float)
    price_high: Mapped[float] = mapped_column(Float)
    type: Mapped[str] = mapped_column(String(40))   # observed_* | estimated_*
    source: Mapped[str] = mapped_column(String(60)) # e.g. binance_orderbook | estimation_model
    strength: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ScenarioRow(Base):
    __tablename__ = "scenarios"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"), index=True)
    type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSONB)
    confidence: Mapped[float] = mapped_column(Float)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)


class AlertRuleRow(Base):
    __tablename__ = "alert_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_key: Mapped[str] = mapped_column(String(80), default="anon", index=True)
    type: Mapped[str] = mapped_column(String(48))
    symbol: Mapped[str | None] = mapped_column(String(20), index=True)
    params: Mapped[dict] = mapped_column(JSONB, default=dict)
    severity: Mapped[str] = mapped_column(String(12), default="info")
    cooldown_sec: Mapped[int] = mapped_column(Integer, default=300)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AlertEventRow(Base):
    __tablename__ = "alert_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("alert_rules.id", ondelete="SET NULL"), index=True
    )
    type: Mapped[str] = mapped_column(String(48))
    symbol: Mapped[str | None] = mapped_column(String(20))
    severity: Mapped[str] = mapped_column(String(12), default="info")
    message: Mapped[str] = mapped_column(Text)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)


class AgentAuditRow(Base):
    """Request audit for the agent API (migration 0002)."""

    __tablename__ = "agent_audit"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    consumer: Mapped[str] = mapped_column(String(80), index=True)
    method: Mapped[str] = mapped_column(String(8))
    path: Mapped[str] = mapped_column(String(500))
    status: Mapped[int] = mapped_column(Integer)
    request_id: Mapped[str] = mapped_column(String(40), index=True)
    latency_ms: Mapped[float] = mapped_column(Float)
