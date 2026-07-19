# -*- coding: utf-8 -*-
"""Regression tests for official TWSE / TPEx fallbacks."""

from __future__ import annotations

from data_provider.base import DataFetchError
from data_provider.twse_tpex_fetcher import TwseTpexFetcher


def test_tpex_index_survives_twse_endpoint_failure() -> None:
    fetcher = TwseTpexFetcher()

    def fake_get(url: str, **_kwargs):
        if "MI_INDEX" in url:
            raise DataFetchError("TWSE unavailable")
        return [
            {"Date": "2026-07-16", "Close": "250.00", "Open": "248", "High": "251", "Low": "247"},
            {"Date": "2026-07-17", "Close": "255.00", "Open": "250", "High": "256", "Low": "249"},
        ]

    fetcher._get_json_or_list = fake_get  # type: ignore[method-assign]
    result = fetcher.get_main_indices("tw")

    assert result is not None
    assert [item["code"] for item in result] == ["TWOII"]
    assert result[0]["current"] == 255.0


def test_twse_index_survives_tpex_endpoint_failure() -> None:
    fetcher = TwseTpexFetcher()

    def fake_get(url: str, **_kwargs):
        if "tpex_index" in url:
            raise DataFetchError("TPEx unavailable")
        return [
            {
                "指數": "發行量加權股價指數",
                "收盤指數": "23000.25",
                "漲跌點數": "100.5",
                "漲跌百分比": "0.44",
                "漲跌": "+",
            }
        ]

    fetcher._get_json_or_list = fake_get  # type: ignore[method-assign]
    result = fetcher.get_main_indices("tw")

    assert result is not None
    assert [item["code"] for item in result] == ["TWII"]
    assert result[0]["current"] == 23000.25


def test_official_taiwan_market_breadth_aggregates_two_exchanges() -> None:
    fetcher = TwseTpexFetcher()

    def fake_get(url: str, **_kwargs):
        if "STOCK_DAY_ALL" in url:
            return [
                {"Date": "20260717", "Change": "+2.0", "TradeValue": "100000000"},
                {"Date": "20260717", "Change": "-1.0", "TradeValue": "250000000"},
            ]
        return [
            {"Date": "115/07/17", "Change": "0", "TransactionAmount": "300000000"},
            {"Date": "115/07/17", "Change": "+0.5", "TransactionAmount": "400000000"},
        ]

    fetcher._get_json_or_list = fake_get  # type: ignore[method-assign]
    result = fetcher.get_market_breadth()

    assert result is not None
    assert result["up_count"] == 2
    assert result["down_count"] == 1
    assert result["flat_count"] == 1
    assert result["coverage"] == 4
    assert result["total_amount"] == 1_050_000_000.0
