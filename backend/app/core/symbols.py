"""Symbol registry: base ticker <-> coingecko id <-> exchange pairs.

Seeded with the tracked majors; extended dynamically from the CoinGecko
top-market-cap list. Name/symbol collisions resolve to the highest
market-cap candidate.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SymbolInfo:
    symbol: str  # uppercase base ticker, e.g. "BTC"
    coingecko_id: str  # e.g. "bitcoin"
    name: str  # e.g. "Bitcoin"

    @property
    def binance_spot_pair(self) -> str:
        return f"{self.symbol}USDT"

    @property
    def binance_perp_pair(self) -> str:
        return f"{self.symbol}USDT"

    @property
    def bybit_pair(self) -> str:
        return f"{self.symbol}USDT"


# symbol -> (coingecko_id, name)
_SEED: dict[str, tuple[str, str]] = {
    "BTC": ("bitcoin", "Bitcoin"),
    "ETH": ("ethereum", "Ethereum"),
    "SOL": ("solana", "Solana"),
    "XRP": ("ripple", "XRP"),
    "BNB": ("binancecoin", "BNB"),
    "DOGE": ("dogecoin", "Dogecoin"),
    "ADA": ("cardano", "Cardano"),
    "TRX": ("tron", "TRON"),
    "AVAX": ("avalanche-2", "Avalanche"),
    "LINK": ("chainlink", "Chainlink"),
    "USDT": ("tether", "Tether"),
    "USDC": ("usd-coin", "USD Coin"),
}

STABLES: set[str] = {"USDT", "USDC", "DAI", "FDUSD", "TUSD", "USDE", "BUSD", "USDP", "PYUSD"}

_registry: dict[str, SymbolInfo] = {
    sym: SymbolInfo(symbol=sym, coingecko_id=cgid, name=name)
    for sym, (cgid, name) in _SEED.items()
}

# lowercase name/symbol -> symbol, used for news asset extraction
_aliases: dict[str, str] = {}
for _sym, (_cgid, _name) in _SEED.items():
    _aliases[_sym.lower()] = _sym
    _aliases[_name.lower()] = _sym


def all_symbols() -> list[str]:
    return sorted(_registry)


def is_known(symbol: str) -> bool:
    return symbol.upper() in _registry


def resolve(symbol: str) -> SymbolInfo | None:
    return _registry.get(symbol.upper())


def coingecko_id(symbol: str) -> str | None:
    info = resolve(symbol)
    return info.coingecko_id if info else None


def update_from_markets(markets: list[dict]) -> None:
    """Extend/refresh the registry from a CoinGecko /coins/markets payload.

    The payload is ordered by market cap desc, so the first occurrence of a
    symbol wins — resolving collisions in favour of the highest market cap.
    """
    for coin in markets:
        sym = (coin.get("symbol") or "").upper()
        name = coin.get("name") or sym
        cgid = coin.get("id") or ""
        if not sym or not cgid or len(sym) > 12:
            continue
        if sym in _registry:
            # keep existing (higher market cap / seed) mapping, but refresh alias
            _aliases.setdefault(name.lower(), sym)
            continue
        _registry[sym] = SymbolInfo(symbol=sym, coingecko_id=cgid, name=name)
        _aliases.setdefault(sym.lower(), sym)
        _aliases.setdefault(name.lower(), sym)


def alias_map() -> dict[str, str]:
    return dict(_aliases)


def _reset() -> None:
    """Test hook."""
    global _registry, _aliases
    _registry = {
        sym: SymbolInfo(symbol=sym, coingecko_id=cgid, name=name)
        for sym, (cgid, name) in _SEED.items()
    }
    _aliases = {}
    for _sym, (_cgid, _name) in _SEED.items():
        _aliases[_sym.lower()] = _sym
        _aliases[_name.lower()] = _sym
