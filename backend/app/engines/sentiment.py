"""Proprietary per-asset sentiment score (-1..1).

Blends news sentiment, price momentum (1h/24h/7d), volume delta and funding.
This is NOT the alternative.me Fear & Greed index — that is reported
separately with attribution.
"""

from __future__ import annotations

from typing import Any, Optional

DISCLAIMER = (
    "asset_score is SkyBus's own composite estimate (-1..1) from news "
    "sentiment, price momentum, volume delta and funding. It is NOT the "
    "alternative.me Fear & Greed index (reported separately with attribution) "
    "and is not financial advice."
)

_WEIGHTS = {"news": 0.35, "momentum": 0.30, "volume": 0.15, "funding": 0.20}


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def momentum_component(
    change_1h: float | None, change_24h: float | None, change_7d: float | None
) -> Optional[float]:
    """Map percent changes to -1..1 via a saturating scale (10% ~ full)."""
    parts = []
    if change_1h is not None:
        parts.append((change_1h / 3.0, 0.2))
    if change_24h is not None:
        parts.append((change_24h / 8.0, 0.4))
    if change_7d is not None:
        parts.append((change_7d / 15.0, 0.4))
    if not parts:
        return None
    total_w = sum(w for _, w in parts)
    return _clamp(sum(_clamp(v) * w for v, w in parts) / total_w)


def funding_component(funding_rate: float | None) -> Optional[float]:
    """Extreme positive funding => crowded longs => negative lean (contrarian)."""
    if funding_rate is None:
        return None
    return _clamp(-funding_rate / 0.001)


def volume_component(volume_24h: float | None, market_cap: float | None) -> Optional[float]:
    """Volume/mcap turnover mapped around a 5% neutral turnover."""
    if volume_24h is None or not market_cap:
        return None
    turnover = volume_24h / market_cap
    return _clamp((turnover - 0.05) / 0.10)


def label_for(score: float | None) -> str:
    if score is None:
        return "unavailable"
    if score >= 0.35:
        return "greed"
    if score >= 0.1:
        return "mildly positive"
    if score <= -0.35:
        return "fear"
    if score <= -0.1:
        return "mildly negative"
    return "neutral"


def combine(components: dict[str, Optional[float]]) -> Optional[float]:
    parts = [(v, _WEIGHTS[k]) for k, v in components.items() if v is not None]
    if not parts:
        return None
    total_w = sum(w for _, w in parts)
    score = sum(v * w for v, w in parts) / total_w
    return round(_clamp(score), 3)


def build_sentiment_report(
    *,
    news_component: float | None,
    change_1h: float | None,
    change_24h: float | None,
    change_7d: float | None,
    volume_24h: float | None,
    market_cap: float | None,
    funding_rate: float | None,
    fear_greed: dict | None,
    updated_at: str | None,
    stale: bool,
) -> dict[str, Any]:
    components = {
        "news": news_component,
        "momentum": momentum_component(change_1h, change_24h, change_7d),
        "volume": volume_component(volume_24h, market_cap),
        "funding": funding_component(funding_rate),
    }
    score = combine(components)
    return {
        "asset_score": score,
        "label": label_for(score),
        "components": components,
        "market_fear_greed": fear_greed,
        "disclaimer": DISCLAIMER,
        "updated_at": updated_at,
        "stale": stale,
    }
