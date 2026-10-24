"""Pydantic schemas for request bodies and OpenAPI documentation.

Responses are assembled as plain dicts by the routers (they merge live,
cached and degraded payloads), so these models focus on request validation
and on documenting the alert resource.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

AlertType = Literal[
    "price_cross",
    "liquidity_zone",
    "liquidity_sweep",
    "book_imbalance",
    "oi_spike",
    "funding_extreme",
    "volume_spike",
    "liquidation_burst",
    "breaking_news",
    "trend_change",
    "cross_exchange_divergence",
]

Severity = Literal["info", "warning", "critical"]


class AlertCreate(BaseModel):
    type: AlertType
    symbol: Optional[str] = Field(default=None, max_length=20)
    params: dict[str, Any] = Field(default_factory=dict)
    severity: Severity = "info"
    cooldown_sec: int = Field(default=300, ge=30, le=86400)


class AlertRuleOut(BaseModel):
    id: str
    user_key: str
    type: str
    symbol: Optional[str]
    params: dict[str, Any]
    severity: str
    cooldown_sec: int
    active: bool
    created_at: str


class AlertEventOut(BaseModel):
    id: str
    rule_id: Optional[str]
    type: str
    symbol: Optional[str]
    severity: str
    message: str
    triggered_at: str
    acknowledged: bool
