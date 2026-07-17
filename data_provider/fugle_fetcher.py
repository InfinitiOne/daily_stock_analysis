# -*- coding: utf-8 -*-
"""Fugle Market Data provider for Taiwan listed/OTC symbols.

This provider is intentionally limited to canonical Yahoo-style Taiwan symbols:
2330.TW (TWSE) and 6488.TWO (TPEx). It never attempts to service US,
Hong Kong, or mainland-China symbols, so cross-market fallback remains
explicit and auditable.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

import pandas as pd
import requests

from src.services.market_symbol_utils import is_suffix_market_symbol
from .base import BaseFetcher, DataFetchError, STANDARD_COLUMNS
from .realtime_types import RealtimeSource, UnifiedRealtimeQuote

logger = logging.getLogger(__name__)

_FUGLE_BASE_URL = "https://api.fugle.tw/marketdata/v1.0/stock"


def _as_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> Optional[int]:
    number = _as_float(value)
    return int(number) if number is not None else None


def _env_number(name: str, default: float) -> float:
    value = _as_float(os.getenv(name))
    return value if value is not None else default


class FugleFetcher(BaseFetcher):
    """Fetch daily candles and intraday quotes from Fugle Market Data."""

    name = "FugleFetcher"
    priority = 0

    def __init__(
        self,
        api_key: Optional[str] = None,
        priority: Optional[int] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        self._api_key = (api_key if api_key is not None else os.getenv("FUGLE_API_KEY", "")).strip()
        self.priority = int(priority if priority is not None else _env_number("FUGLE_PRIORITY", 0))
        self._timeout_seconds = max(1.0, _env_number("FUGLE_TIMEOUT_SECONDS", 12.0))
        self._session = session or requests.Session()

    def is_available(self, capability: str = "") -> bool:
        """Only register Fugle when a key is present; do not probe the remote API."""
        return bool(self._api_key)

    @staticmethod
    def _symbol(stock_code: str) -> str:
        code = (stock_code or "").strip().upper()
        if not is_suffix_market_symbol(code, "tw"):
            raise DataFetchError(f"[Fugle] {stock_code} is not a Taiwan .TW/.TWO symbol")
        return code.rsplit(".", 1)[0]

    def _request(self, path: str, *, params: Optional[dict[str, Any]] = None) -> Any:
        if not self._api_key:
            raise DataFetchError("[Fugle] API key is not configured")

        try:
            response = self._session.get(
                f"{_FUGLE_BASE_URL}/{path.lstrip('/')}",
                headers={"X-API-KEY": self._api_key},
                params=params,
                timeout=self._timeout_seconds,
            )
        except requests.RequestException as exc:
            raise DataFetchError(f"[Fugle] request failed: {type(exc).__name__}") from exc

        if response.status_code in (401, 403):
            raise DataFetchError("[Fugle] authentication or plan permission was rejected")
        if response.status_code == 429:
            raise DataFetchError("[Fugle] rate limit reached")
        try:
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise DataFetchError(f"[Fugle] invalid API response: {type(exc).__name__}") from exc

        if isinstance(payload, Mapping) and payload.get("error"):
            raise DataFetchError("[Fugle] API returned an error response")
        return payload

    @staticmethod
    def _data(payload: Any) -> Any:
        if isinstance(payload, Mapping) and "data" in payload:
            return payload["data"]
        return payload

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        symbol = self._symbol(stock_code)
        payload = self._request(
            f"historical/candles/{symbol}",
            params={
                "from": start_date,
                "to": end_date,
                "timeframe": "D",
                "adjusted": "false",
                "fields": "date,open,high,low,close,volume,turnover,change",
                "sort": "asc",
            },
        )
        rows = self._data(payload)
        if not isinstance(rows, list) or not rows:
            raise DataFetchError(f"[Fugle] no historical candles returned for {symbol}")
        return pd.DataFrame(rows)

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        normalized = df.copy()
        required = {"date", "open", "high", "low", "close", "volume"}
        missing = required.difference(normalized.columns)
        if missing:
            raise DataFetchError(f"[Fugle] historical response missing fields: {', '.join(sorted(missing))}")

        normalized["amount"] = normalized.get("turnover")
        previous_close = normalized["close"].shift(1)
        normalized["pct_chg"] = (
            (normalized["close"] - previous_close) / previous_close.replace(0, pd.NA) * 100
        )
        normalized["pct_chg"] = normalized["pct_chg"].fillna(0)
        normalized["code"] = stock_code.strip().upper()
        keep = ["code", *STANDARD_COLUMNS]
        return normalized[[column for column in keep if column in normalized.columns]]

    @staticmethod
    def _provider_timestamp(value: Any) -> Optional[str]:
        numeric = _as_float(value)
        if numeric is not None:
            try:
                return datetime.fromtimestamp(numeric / 1000, tz=timezone.utc).isoformat()
            except (OverflowError, OSError, ValueError):
                return None
        return str(value) if value else None

    def get_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        try:
            symbol = self._symbol(stock_code)
            payload = self._data(self._request(f"intraday/quote/{symbol}"))
        except DataFetchError as exc:
            logger.warning("[Fugle] realtime quote unavailable for %s: %s", stock_code, exc)
            return None

        if not isinstance(payload, Mapping):
            logger.warning("[Fugle] realtime quote response has unexpected format for %s", stock_code)
            return None

        total = payload.get("total") if isinstance(payload.get("total"), Mapping) else {}
        price = _as_float(payload.get("lastPrice"))
        if price is None:
            price = _as_float(payload.get("closePrice"))
        if price is None or price <= 0:
            return None

        previous_close = _as_float(payload.get("previousClose"))
        high = _as_float(payload.get("highPrice"))
        low = _as_float(payload.get("lowPrice"))
        amplitude = None
        if high is not None and low is not None and previous_close and previous_close > 0:
            amplitude = round((high - low) / previous_close * 100, 4)

        return UnifiedRealtimeQuote(
            code=stock_code.strip().upper(),
            name=str(payload.get("name") or ""),
            source=RealtimeSource.FUGLE,
            market="tw",
            currency="TWD",
            data_quality="ok",
            provider_timestamp=self._provider_timestamp(payload.get("lastUpdated")),
            price=price,
            change_pct=_as_float(payload.get("changePercent")),
            change_amount=_as_float(payload.get("change")),
            volume=_as_int(total.get("tradeVolume")),
            amount=_as_float(total.get("tradeValue")),
            amplitude=amplitude,
            open_price=_as_float(payload.get("openPrice")),
            high=high,
            low=low,
            pre_close=previous_close,
        )
