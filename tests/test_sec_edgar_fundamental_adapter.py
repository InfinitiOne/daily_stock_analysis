# -*- coding: utf-8 -*-
"""Tests for the public SEC EDGAR fundamental fallback."""

from __future__ import annotations

from typing import Any

from data_provider.sec_edgar_fundamental_adapter import SecEdgarFundamentalAdapter


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

    def get(self, url: str, **_kwargs: Any) -> _Response:
        for fragment, payload in self.payloads.items():
            if fragment in url:
                return _Response(payload)
        raise AssertionError(f"unexpected URL: {url}")


def _annual(value: float, end: str, filed: str) -> dict[str, Any]:
    return {"val": value, "form": "10-K", "fp": "FY", "end": end, "filed": filed, "accn": filed}


def test_sec_edgar_returns_only_reported_company_facts() -> None:
    SecEdgarFundamentalAdapter._ticker_cache = None
    SecEdgarFundamentalAdapter._facts_cache.clear()
    session = _Session(
        {
            "company_tickers": {"0": {"ticker": "NVDA", "cik_str": 1045810}},
            "CIK0001045810": {
                "facts": {
                    "us-gaap": {
                        "RevenueFromContractWithCustomerExcludingAssessedTax": {
                            "units": {"USD": [_annual(100.0, "2024-01-31", "2024-03-01"), _annual(150.0, "2025-01-31", "2025-03-01")]}
                        },
                        "NetIncomeLoss": {
                            "units": {"USD": [_annual(20.0, "2024-01-31", "2024-03-01"), _annual(45.0, "2025-01-31", "2025-03-01")]}
                        },
                        "NetCashProvidedByUsedInOperatingActivities": {
                            "units": {"USD": [_annual(50.0, "2025-01-31", "2025-03-01")]}
                        },
                    }
                }
            },
        }
    )

    bundle = SecEdgarFundamentalAdapter(session=session).get_fundamental_bundle("NVDA")

    assert bundle["status"] == "partial"
    assert bundle["growth"]["revenue_yoy"] == 50.0
    assert bundle["earnings"]["financial_report"]["revenue"] == 150.0
    assert bundle["earnings"]["financial_report"]["net_income_loss"] == 45.0


def test_sec_edgar_metadata_without_amounts_is_not_treated_as_data() -> None:
    SecEdgarFundamentalAdapter._ticker_cache = None
    SecEdgarFundamentalAdapter._facts_cache.clear()
    session = _Session(
        {
            "company_tickers": {"0": {"ticker": "NVDA", "cik_str": 1045810}},
            "CIK0001045810": {"facts": {"us-gaap": {}}},
        }
    )

    bundle = SecEdgarFundamentalAdapter(session=session).get_fundamental_bundle("NVDA")

    assert bundle["status"] == "not_supported"
    assert bundle["growth"] == {}
    assert bundle["earnings"] == {}
    assert "沒有可用" in bundle["errors"][0]
