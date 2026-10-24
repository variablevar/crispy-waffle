"""Headline categorizer: keyword rules -> news_category enum, asset
extraction, importance scoring (1..5), sentiment lexicon (-1..1) and
news_kind classification. Pure functions — no network."""

from __future__ import annotations

import re
import string
from difflib import SequenceMatcher

from app.core import symbols as symbol_registry

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "halving": ("halving", "block reward halv", "reward halv"),
    "token_unlock": ("token unlock", "unlock schedule", "vesting unlock", "cliff unlock", "token vesting"),
    "token_burn": ("token burn", "burns ", "burned", "buyback and burn", "supply burn"),
    "exchange_listing": ("will list", "listing", "listed on", "new trading pair", "adds support for"),
    "delisting": ("delist", "delisting", "removes trading pair", "cease trading"),
    "binance_update": ("binance announcement", "binance will", "binance has", "binance support", "binance futures", "binance spot"),
    "bybit_update": ("bybit announcement", "bybit will", "bybit has", "bybit support"),
    "regulation": ("sec ", "cftc", "regulator", "regulation", "lawsuit", "court", "ban ", "banned", "legal", "compliance", "mica", "senate", "congress", "doj", "settlement", "fine ", "fined"),
    "etf": ("etf", "exchange-traded fund", "spot bitcoin fund", "spot ether"),
    "whale": ("whale", "large transfer", "dormant wallet", "moves $", "moved $", "accumulat"),
    "hack": ("hack", "exploit", "breach", "stolen", "drained", "vulnerability", "attack", "rug pull", "rugpull", "phishing"),
    "protocol_upgrade": ("upgrade", "hard fork", "hardfork", "mainnet launch", "testnet", "fork", "eip-", "improvement proposal", "v2 launch", "v3 launch"),
    "defi": ("defi", "tvl", "yield", "staking", "lending protocol", "liquidity pool", "amm", "dex ", "uniswap", "aave", "curve"),
    "liquidity": ("liquidity", "liquidation", "liquidated", "open interest", "funding rate", "market depth", "order book"),
    "macro": ("fed ", "fomc", "interest rate", "inflation", "cpi", "jobs report", "recession", "treasury", "dollar", "macro", "powell", "rate cut", "rate hike"),
    "partnership": ("partnership", "partners with", "collaborat", "integrat", "teams up", "joins forces"),
}

# high-impact categories push importance up
_CATEGORY_IMPACT = {
    "hack": 5, "regulation": 4, "etf": 4, "halving": 4, "delisting": 4,
    "exchange_listing": 3, "token_unlock": 3, "liquidation": 4,
}

_POSITIVE = {
    "surge", "soar", "rally", "rallies", "gain", "gains", "bullish", "record", "high",
    "jump", "jumps", "rise", "rises", "breakout", "approve", "approved", "approval",
    "adoption", "partnership", "upgrade", "boost", "rebound", "recover", "recovery",
    "outperform", "milestone", "all-time high", "ath", "green", "up ", "profit",
    "accumulate", "inflow", "inflows", "buying", "growth", "win", "wins", "launch",
}
_NEGATIVE = {
    "crash", "plunge", "plunges", "drop", "drops", "fall", "falls", "bearish", "low",
    "dump", "dumps", "selloff", "sell-off", "hack", "hacked", "exploit", "ban", "banned",
    "lawsuit", "sue", "sued", "fear", "panic", "liquidat", "outflow", "outflows",
    "fraud", "scam", "collapse", "bankrupt", "delisting", "delist", "down ", "loss",
    "losses", "warning", "risk", "crisis", "fine", "fined", "red", "correction",
}

_RUMOUR_KEYWORDS = ("rumour", "rumor", "allegedly", "unconfirmed", "sources say", "reportedly", "leak", "speculat")
_OPINION_KEYWORDS = ("opinion", "op-ed", "oped", "editorial", "commentary", "blog", "why i think", "my take", "perspective")
_ANNOUNCEMENT_HINTS = ("announcement", "official", "will list", "will delist", "upgrade notice", "maintenance")
# engines prefix their own generated items
_ANALYSIS_PREFIX = "analysis:"


def normalize_headline(headline: str) -> str:
    text = headline.lower().strip()
    text = text.translate(str.maketrans("", "", string.punctuation))
    return re.sub(r"\s+", " ", text)


def headline_similarity(a: str, b: str) -> float:
    """0..1 similarity of two normalized headlines."""
    return SequenceMatcher(None, normalize_headline(a), normalize_headline(b)).ratio()


def classify_category(headline: str, summary: str | None = None) -> str:
    text = f"{headline} {summary or ''}".lower()
    # binance/bybit announcements take priority over generic listing keywords
    for category in ("binance_update", "bybit_update"):
        if any(k in text for k in CATEGORY_KEYWORDS[category]):
            return category
    best, best_hits = "general", 0
    for category, keywords in CATEGORY_KEYWORDS.items():
        hits = sum(1 for k in keywords if k in text)
        if hits > best_hits or (hits == best_hits and hits > 0 and _tie_wins(category, best)):
            best, best_hits = category, hits
    return best


# On a keyword-count tie, specific market events beat broad themes
# ("SEC approves spot ETF" is ETF news that happens to involve a regulator).
_TIE_PRIORITY = (
    "halving", "token_unlock", "token_burn", "exchange_listing", "delisting",
    "etf", "hack", "protocol_upgrade", "whale", "defi", "liquidity",
    "partnership", "regulation", "macro",
)


def _tie_wins(candidate: str, current: str) -> bool:
    try:
        return _TIE_PRIORITY.index(candidate) < _TIE_PRIORITY.index(current)
    except ValueError:
        return False


def extract_assets(text: str) -> list[str]:
    """Extract base tickers mentioned in the text via the symbol/name dictionary."""
    lowered = text.lower()
    tokens = set(re.findall(r"[a-z0-9$]+", lowered))
    found: list[str] = []
    for alias, sym in symbol_registry.alias_map().items():
        if len(alias) <= 4:
            if alias in tokens or f"${alias}" in tokens:
                found.append(sym)
        elif alias in lowered:
            found.append(sym)
    # dedupe, preserve order
    seen: set[str] = set()
    out: list[str] = []
    for sym in found:
        if sym not in seen:
            seen.add(sym)
            out.append(sym)
    return out


def sentiment_score(text: str) -> float:
    """Lexicon-based sentiment estimate in -1..1. This is an estimate, not
    a verified label."""
    lowered = text.lower()
    pos = sum(1 for w in _POSITIVE if w in lowered)
    neg = sum(1 for w in _NEGATIVE if w in lowered)
    total = pos + neg
    if total == 0:
        return 0.0
    score = (pos - neg) / total
    return max(-1.0, min(1.0, round(score, 3)))


def importance_score(headline: str, category: str, assets: list[str]) -> int:
    """1..5 importance heuristic."""
    score = 3
    score = max(score, _CATEGORY_IMPACT.get(category, 3))
    majors = {"BTC", "ETH"}
    if majors.intersection(assets):
        score = max(score, 4) if category in _CATEGORY_IMPACT else score
    if len(assets) >= 3:
        score = min(5, score + 1)
    text = headline.lower()
    if any(k in text for k in ("breaking", "urgent", "just in", "flash")):
        score = min(5, score + 1)
    return max(1, min(5, score))


def classify_kind(headline: str, source_name: str | None = None) -> str:
    """verified | opinion | rumour | analysis.

    - engine-generated items are prefixed and become 'analysis'
    - rumour/opinion keyword detection
    - wire/announcement items default to 'verified'
    """
    text = headline.lower()
    if text.startswith(_ANALYSIS_PREFIX):
        return "analysis"
    if any(k in text for k in _RUMOUR_KEYWORDS):
        return "rumour"
    if any(k in text for k in _OPINION_KEYWORDS):
        return "opinion"
    src = (source_name or "").lower()
    if any(k in text for k in _ANNOUNCEMENT_HINTS) or "announcement" in src:
        return "verified"
    return "verified"
