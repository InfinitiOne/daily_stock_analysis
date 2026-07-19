# -*- coding: utf-8 -*-
"""Regression coverage for auditable public-data fallback routes."""

from __future__ import annotations

import pandas as pd

from data_provider.base import DataFetcherManager


class _DailyFetcher:
    def __init__(self, name: str, *, frame: pd.DataFrame | None = None, error: Exception | None = None) -> None:
        self.name = name
        self.priority = 1
        self._frame = frame
        self._error = error

    def is_available(self, *_args, **_kwargs) -> bool:
        return True

    def get_daily_data(self, **_kwargs):
        if self._error is not None:
            raise self._error
        return self._frame


class _IndexFetcher:
    def __init__(self, name: str, rows: list[dict]) -> None:
        self.name = name
        self.priority = 1
        self._rows = rows

    def get_main_indices(self, *, region: str):
        assert region == "tw"
        return self._rows


def _manager_with(fetchers):
    manager = DataFetcherManager.__new__(DataFetcherManager)
    manager._fetchers = list(fetchers)
    manager._fetchers_by_name = {fetcher.name: fetcher for fetcher in fetchers}
    return manager


def test_taiwan_daily_trace_shows_api_skips_failure_and_official_recovery() -> None:
    frame = pd.DataFrame(
        [{"date": "2026-07-17", "open": 100, "high": 101, "low": 99, "close": 100, "volume": 10}]
    )
    manager = _manager_with(
        [
            _DailyFetcher("YfinanceFetcher", error=RuntimeError("Yahoo unavailable")),
            _DailyFetcher("TwseTpexFetcher", frame=frame),
        ]
    )

    result, source = manager.get_daily_data("2330.TW", days=30)
    trace = {item["provider"]: item for item in manager.get_daily_source_trace("2330.TW")}

    assert not result.empty
    assert source == "TwseTpexFetcher"
    assert trace["FugleFetcher"]["status"] == "skipped"
    assert trace["FinMindFetcher"]["status"] == "skipped"
    assert trace["YfinanceFetcher"]["status"] == "failed"
    assert trace["TwseTpexFetcher"]["status"] == "success"


def test_taiwan_index_status_distinguishes_twse_and_tpex_success() -> None:
    manager = _manager_with(
        [
            _IndexFetcher(
                "TwseTpexFetcher",
                [
                    {"code": "TWII", "current": 23000.0},
                    {"code": "TWOII", "current": 255.0},
                ],
            )
        ]
    )

    data, source = manager.get_main_indices_with_source("tw")
    status = {item["provider"]: item for item in manager.get_main_index_source_status("tw")}

    assert {item["code"] for item in data} == {"TWII", "TWOII"}
    assert source == "TwseTpexFetcher"
    assert status["TWSE"]["status"] == "success"
    assert status["TPEx"]["status"] == "success"
