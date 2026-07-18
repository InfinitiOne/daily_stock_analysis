# -*- coding: utf-8 -*-
"""Public Stooq CSV fallback for US daily OHLCV.

The provider is intentionally last in the US route.  It has no key, which
makes it useful when the configured market-data APIs and Yahoo Finance are all
temporarily unavailable.  It is not used for intraday quotes or as a source of
company fundamentals.
"""

from __future__ import annotations

from io import StringIO
import logging
import os
from typing import Optional

import pandas as pd
import requests

from .base import BaseFetcher, DataFetchError, STANDARD_COLUMNS
from .us_index_mapping import is_us_stock_code


logger = logging.getLogger(__name__)
_STOOQ_DAILY_URL = "https://stooq.com/q/d/l/"


class StooqFetcher(BaseFetcher):
    """No-key last-resort US end-of-day historical-price provider."""

    name = "StooqFetcher"
    priority = 9

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self._session = session or requests.Session()
        self._timeout_seconds = max(2.0, float(os.getenv("STOOQ_TIMEOUT_SECONDS", "15")))

    def is_available(self, capability: str = "") -> bool:
        return True

    @staticmethod
    def _symbol(stock_code: str) -> str:
        code = (stock_code or "").strip().upper()
        if not is_us_stock_code(code):
            raise DataFetchError(f"[Stooq] {stock_code} is not a supported US equity symbol")
        return f"{code.lower().replace('.', '-')}.us"

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        try:
            response = self._session.get(
                _STOOQ_DAILY_URL,
                params={"s": self._symbol(stock_code), "i": "d"},
                headers={"User-Agent": "JEAC-Enterprise/5.0"},
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            df = pd.read_csv(StringIO(response.text))
        except (requests.RequestException, ValueError, pd.errors.ParserError) as exc:
            raise DataFetchError(f"[Stooq] public CSV request failed: {type(exc).__name__}") from exc
        required = {"Date", "Open", "High", "Low", "Close", "Volume"}
        if not required.issubset(df.columns):
            raise DataFetchError(f"[Stooq] no daily OHLCV returned for {stock_code}")
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        start, end = pd.Timestamp(start_date), pd.Timestamp(end_date)
        return df[(df["Date"] >= start) & (df["Date"] <= end)].copy()

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        normalized = df.rename(columns={
            "Date": "date", "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        }).copy()
        normalized["amount"] = 0.0
        normalized["pct_chg"] = normalized["close"].pct_change().fillna(0.0) * 100
        normalized["code"] = stock_code.strip().upper()
        return normalized[["code", *STANDARD_COLUMNS]]
