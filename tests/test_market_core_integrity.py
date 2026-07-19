# -*- coding: utf-8 -*-
"""Core market-data gates must reject named but price-less indices."""

from __future__ import annotations

from types import SimpleNamespace

from src.market_analyzer import MarketAnalyzer, MarketIndex, MarketOverview


def test_core_integrity_requires_a_real_positive_index_value() -> None:
    analyzer = MarketAnalyzer.__new__(MarketAnalyzer)
    analyzer.profile = SimpleNamespace(required_index_codes=("TWII", "TWOII"))
    analyzer._last_index_source = "TWSE/TPEx"
    overview = MarketOverview(
        date="2026-07-19",
        index_source="TWSE/TPEx",
        indices=[
            MarketIndex(code="TWII", name="臺灣加權指數", current=23000.0),
            MarketIndex(code="TWOII", name="櫃買指數", current=None),
        ],
    )

    integrity = analyzer.get_market_data_integrity(overview)

    assert integrity["status"] == "unavailable"
    assert integrity["received_indices"] == ["TWII"]
    assert integrity["missing_indices"] == ["TWOII"]


def test_core_integrity_accepts_all_required_positive_prices() -> None:
    analyzer = MarketAnalyzer.__new__(MarketAnalyzer)
    analyzer.profile = SimpleNamespace(required_index_codes=("SPX", "IXIC", "SOX", "VIX"))
    analyzer._last_index_source = "NasdaqWebFetcher"
    overview = MarketOverview(
        date="2026-07-19",
        index_source="NasdaqWebFetcher",
        indices=[
            MarketIndex(code="SPX", name="S&P 500", current=6200.0),
            MarketIndex(code="IXIC", name="NASDAQ", current=20000.0),
            MarketIndex(code="SOX", name="費城半導體", current=5200.0),
            MarketIndex(code="VIX", name="VIX", current=16.0),
        ],
    )

    integrity = analyzer.get_market_data_integrity(overview)

    assert integrity["status"] == "available"
    assert integrity["missing_indices"] == []
