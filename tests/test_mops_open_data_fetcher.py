# -*- coding: utf-8 -*-
"""Tests for the no-key official MOPS fundamental-data fallback."""

from __future__ import annotations

from typing import Any

from data_provider.mops_open_data_fetcher import MopsOpenDataFetcher


class _Response:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


class _Session:
    def __init__(self, payloads: dict[str, Any]) -> None:
        self.payloads = payloads
        self.urls: list[str] = []

    def get(self, url: str, **_kwargs: Any) -> _Response:
        self.urls.append(url)
        for suffix, payload in self.payloads.items():
            if url.endswith(suffix):
                return _Response(payload)
        raise AssertionError(f"unexpected URL: {url}")


def test_mops_fills_official_company_revenue_and_financial_fields() -> None:
    MopsOpenDataFetcher._cache.clear()
    session = _Session(
        {
            "t187ap05_L": [
                {
                    "公司代號": "2330",
                    "資料年月": "11506",
                    "營業收入-當月營收": "263709000",
                    "營業收入-上月比較增減(%)": "1.2",
                    "營業收入-去年同月增減(%)": "40.1",
                    "累計營業收入-前期比較增減(%)": "38.0",
                    "產業別": "半導體業",
                }
            ],
            "t187ap14_L": [
                {
                    "公司代號": "2330",
                    "年度": "115",
                    "季別": "1",
                    "營業收入": "839254000",
                    "營業利益": "400000000",
                    "稅後淨利": "300000000",
                    "基本每股盈餘(元)": "12.34",
                }
            ],
        }
    )

    bundle = MopsOpenDataFetcher(session=session).get_fundamental_bundle("2330.TW")

    assert bundle["status"] == "partial"
    assert bundle["growth"]["monthly_revenue"]["monthly_revenue_yoy_pct"] == 40.1
    assert bundle["earnings"]["financial_report"]["basic_eps"] == 12.34
    assert bundle["earnings"]["financial_report"]["report_date"] == "2026-Q1"
    assert bundle["earnings"]["financial_report"]["revenue"] == 839254000000.0
    assert bundle["earnings"]["financial_report"]["net_profit_parent"] == 300000000000.0
    assert bundle["source_chain"][0]["provider"] == "MOPS Open Data（TWSE OpenAPI）"


def test_mops_does_not_claim_metadata_only_rows_are_financial_data() -> None:
    MopsOpenDataFetcher._cache.clear()
    session = _Session(
        {
            "t187ap05_L": [{"公司代號": "2330", "資料年月": "11506", "產業別": "半導體業"}],
            "t187ap14_L": [{"公司代號": "2330", "年度": "115", "季別": "1"}],
        }
    )

    bundle = MopsOpenDataFetcher(session=session).get_fundamental_bundle("2330.TW")

    assert bundle["growth"] == {}
    assert bundle["earnings"] == {}
    # The industry classification remains useful evidence, but it must not
    # become a made-up revenue/earnings figure.
    assert bundle["belong_boards"] == [{"name": "半導體業", "type": "產業"}]


def test_mops_marks_etf_fundamentals_as_not_applicable_without_request() -> None:
    MopsOpenDataFetcher._cache.clear()
    session = _Session({})

    bundle = MopsOpenDataFetcher(session=session).get_fundamental_bundle("00940.TW")

    assert bundle["status"] == "not_supported"
    assert bundle["errors"] == ["ETF 不適用公司月營收與財報欄位"]
    assert session.urls == []
