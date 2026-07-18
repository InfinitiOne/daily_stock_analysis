# -*- coding: utf-8 -*-
"""Tests for the no-key Nasdaq / FRED public data fallback."""

from __future__ import annotations

from typing import Any

from data_provider.nasdaq_web_fetcher import NasdaqWebFetcher


class _Response:
    text = "observation_date,SP500\n2026-07-16,6200.10\n2026-07-17,6210.20\n"

    def raise_for_status(self) -> None:
        return None


class _Session:
    def get(self, _url: str, **_kwargs: Any) -> _Response:
        return _Response()


def test_fred_close_only_series_does_not_invent_ohlc_or_volume() -> None:
    rows = NasdaqWebFetcher(session=_Session())._fred_rows(
        "SPX", start_date="2026-07-01", end_date="2026-07-31"
    )

    assert len(rows) == 2
    assert rows[-1]["close"] == 6210.2
    assert rows[-1]["open"] is None
    assert rows[-1]["high"] is None
    assert rows[-1]["low"] is None
    assert rows[-1]["source_fields"]["volume"] == "未取得"
