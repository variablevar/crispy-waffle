"""Contract normalization: linear vs inverse derivatives, premium and basis.

Units are stated per function. Conventions:
- linear (USDT-margined) contracts: quantity is denominated in the BASE asset
  (e.g. BTC); quote volume = qty x price.
- inverse (coin-margined) contracts: quantity is a count of CONTRACTS, each
  worth `contract_size` units of QUOTE currency (e.g. USD); quote volume =
  contracts x contract_size, base volume = quote volume / price.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

ContractType = Literal["linear", "inverse"]


def normalize_volume(
    qty: float,
    price: float,
    contract_type: ContractType = "linear",
    contract_size: Optional[float] = None,
) -> dict[str, float]:
    """Normalize a traded quantity to base and quote volumes.

    Units:
    - linear: `qty` in BASE asset. Returns base_volume=qty,
      quote_volume=qty*price (both in base / quote units respectively).
    - inverse: `qty` in CONTRACTS, `contract_size` in QUOTE currency per
      contract (e.g. 100 USD). Returns quote_volume=qty*contract_size,
      base_volume=quote_volume/price.

    Example: 1000 inverse contracts x $100 at price 50_000 ->
    quote_volume $100_000, base_volume 2.0 BTC.

    Raises ValueError on non-positive price, or inverse without contract_size.
    """
    if price <= 0:
        raise ValueError("price must be positive")
    if contract_type == "linear":
        base_volume = float(qty)
        quote_volume = float(qty) * price
    elif contract_type == "inverse":
        if not contract_size or contract_size <= 0:
            raise ValueError("inverse contracts require a positive contract_size")
        quote_volume = float(qty) * float(contract_size)
        base_volume = quote_volume / price
    else:
        raise ValueError(f"unknown contract_type: {contract_type!r}")
    return {
        "base_volume": base_volume,
        "quote_volume": quote_volume,
        "contract_type": contract_type,
    }


def perp_premium_pct(perp_price: float, spot_price: float) -> Optional[float]:
    """Perp premium over spot in PERCENT: (perp - spot) / spot * 100.

    Positive = perp trading above spot (contango). None when inputs are
    missing or non-positive.
    """
    if not perp_price or not spot_price or perp_price <= 0 or spot_price <= 0:
        return None
    return round((perp_price - spot_price) / spot_price * 100.0, 5)


def basis(perp_price: float, spot_price: float) -> dict[str, Any]:
    """Basis between perp and spot.

    Returns absolute basis in QUOTE currency (perp_price - spot_price) and
    pct basis in PERCENT. Both None when inputs are unusable.
    """
    if not perp_price or not spot_price or perp_price <= 0 or spot_price <= 0:
        return {"absolute": None, "pct": None}
    return {
        "absolute": round(perp_price - spot_price, 8),
        "pct": perp_premium_pct(perp_price, spot_price),
    }
