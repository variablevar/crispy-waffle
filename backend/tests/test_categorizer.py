"""News categorizer: category mapping, asset extraction, dedupe, kind, bounds."""

from __future__ import annotations

from app.engines import categorizer


def test_category_mapping():
    assert categorizer.classify_category("Bitcoin halving expected in April") == "halving"
    assert categorizer.classify_category("Coinbase will list NewToken (NEW)") == "exchange_listing"
    assert categorizer.classify_category("Binance will list NewToken (NEW)") == "binance_update"
    assert categorizer.classify_category("SEC approves spot ETF application") == "etf"
    assert categorizer.classify_category("Exchange hacked, $50M stolen in exploit") == "hack"
    assert categorizer.classify_category("Fed raises interest rates amid inflation") == "macro"
    assert categorizer.classify_category("Token unlock schedule released") == "token_unlock"


def test_extract_assets_by_symbol_and_name():
    assets = categorizer.extract_assets("BTC and Ethereum rally while Solana slips")
    assert "BTC" in assets
    assert "ETH" in assets
    assert "SOL" in assets


def test_sentiment_score_sign():
    assert categorizer.sentiment_score("Bitcoin surges to record high on strong demand") > 0
    assert categorizer.sentiment_score("Market crashes as panic selling intensifies") < 0


def test_importance_bounds():
    score = categorizer.importance_score("Minor blog post", "general", [])
    assert 1 <= score <= 5
    big = categorizer.importance_score("SEC approves Bitcoin ETF", "etf", ["BTC"])
    assert 1 <= big <= 5
    assert big >= score


def test_kind_classification():
    assert categorizer.classify_kind("Rumour: exchange insolvent") == "rumour"
    assert categorizer.classify_kind("Opinion: why BTC is undervalued") == "opinion"


def test_syndicated_headline_dedupe_similarity():
    a = categorizer.normalize_headline("Bitcoin ETF Approved by SEC!")
    b = categorizer.normalize_headline("Bitcoin ETF approved by SEC")
    assert a == b
    assert categorizer.headline_similarity(a, b) >= 0.85
    c = categorizer.normalize_headline("Solana network upgrade goes live")
    assert categorizer.headline_similarity(a, c) < 0.85
