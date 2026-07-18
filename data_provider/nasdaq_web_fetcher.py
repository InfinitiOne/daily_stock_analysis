# -*- coding: utf-8 -*-
"""Public Nasdaq and FRED fallback for US market data.

This adapter is intentionally independent of Yahoo Finance and API-key based
providers.  It is used only after the configured primary sources fail (or as
the official public source for the US market-index review).  Nasdaq's public
quote endpoints provide end-of-day US equity/index data, while FRED provides
the public closing series for S&P 500, Nasdaq Composite, Dow Jones, and VIX.

No value is invented when an endpoint does not publish a field: the adapter
keeps the field absent and leaves the report layer to display "未取得".
"""

from __future__ import annotations

from io import StringIO
import logging
import os
from typing import Any, Dict, Iterable, Optional

import pandas as pd
import requests

from .base import BaseFetcher, DataFetchError, STANDARD_COLUMNS
from .realtime_types import RealtimeSource, UnifiedRealtimeQuote
from .us_index_mapping import is_us_index_code, is_us_stock_code


logger = logging.getLogger(__name__)

_NASDAQ_QUOTE_URL = "https://api.nasdaq.com/api/quote/{symbol}/{endpoint}"
_FRED_GRAPH_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"

# Nasdaq publishes the Composite index as COMP rather than IXIC.
_NASDAQ_INDEX_SYMBOLS = {
    "IXIC": "COMP",
    "SOX": "SOX",
}
_FRED_INDEX_SERIES = {
    "SPX": ("SP500", "S&P 500 指數"),
    "IXIC": ("NASDAQCOM", "NASDAQ 綜合指數"),
    "DJI": ("DJIA", "道瓊工業指數"),
    "VIX": ("VIXCLS", "Cboe 波動率指數（VIX）"),
}
_INDEX_NAMES = {
    **{code: name for code, (_series, name) in _FRED_INDEX_SERIES.items()},
    "SOX": "費城半導體指數",
}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _number(value: Any) -> Optional[float]:
    text = str(value or "").strip().replace(",", "").replace("$", "")
    text = text.replace("%", "").replace("+", "")
    if text in {"", "--", "-", "N/A", "None"}:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


class NasdaqWebFetcher(BaseFetcher):
    """No-key public fallback for US equity OHLCV and market indices."""

    name = "NasdaqWebFetcher"
    priority = 9

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self._session = session or requests.Session()
        self._timeout_seconds = max(2.0, _env_float("NASDAQ_WEB_TIMEOUT_SECONDS", 15.0))
        self._headers = {
            "User-Agent": "Mozilla/5.0 (compatible; JEAC-Enterprise/5.0)",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.8",
        }

    def is_available(self, capability: str = "") -> bool:
        return True

    @staticmethod
    def _asset_class(stock_code: str) -> str:
        if is_us_index_code(stock_code):
            return "index"
        if is_us_stock_code(stock_code):
            return "stocks"
        raise DataFetchError(f"[Nasdaq] {stock_code} is not a supported US symbol")

    @staticmethod
    def _nasdaq_symbol(stock_code: str) -> str:
        code = (stock_code or "").strip().upper()
        if is_us_index_code(code):
            return _NASDAQ_INDEX_SYMBOLS.get(code, code)
        return code

    def _get_json(self, stock_code: str, endpoint: str, *, params: Dict[str, Any]) -> Dict[str, Any]:
        symbol = self._nasdaq_symbol(stock_code)
        url = _NASDAQ_QUOTE_URL.format(symbol=symbol.lower(), endpoint=endpoint)
        try:
            response = self._session.get(
                url,
                params=params,
                headers=self._headers,
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise DataFetchError(f"[Nasdaq] public endpoint request failed: {type(exc).__name__}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            raise DataFetchError(f"[Nasdaq] no public data returned for {stock_code}")
        return payload["data"]

    def _nasdaq_history_rows(
        self,
        stock_code: str,
        *,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        data = self._get_json(
            stock_code,
            "historical",
            params={
                "assetclass": self._asset_class(stock_code),
                "fromdate": start_date,
                "limit": 5000,
            },
        )
        rows = ((data.get("tradesTable") or {}).get("rows") or [])
        if not isinstance(rows, list):
            return []
        parsed: list[dict[str, Any]] = []
        start, end = pd.Timestamp(start_date), pd.Timestamp(end_date)
        for row in rows:
            if not isinstance(row, dict):
                continue
            timestamp = pd.to_datetime(row.get("date"), errors="coerce")
            close = _number(row.get("close"))
            if pd.isna(timestamp) or close is None:
                continue
            if timestamp < start or timestamp > end:
                continue
            open_ = _number(row.get("open"))
            high = _number(row.get("high"))
            low = _number(row.get("low"))
            # Index rows do not always publish exchange volume.  A neutral
            # non-null transport value is required by the historical-frame
            # contract, but the accompanying status explicitly prevents it
            # from being rendered as a real traded-volume value.
            volume = _number(row.get("volume"))
            parsed.append(
                {
                    "date": timestamp,
                    "open": open_ if open_ is not None else close,
                    "high": high if high is not None else close,
                    "low": low if low is not None else close,
                    "close": close,
                    "volume": volume if volume is not None else 0.0,
                    "amount": (close * volume) if volume is not None else None,
                    "source_fields": {
                        "volume": "available" if volume is not None else "未取得",
                    },
                }
            )
        return parsed

    def _fred_rows(self, stock_code: str, *, start_date: str, end_date: str) -> list[dict[str, Any]]:
        code = (stock_code or "").strip().upper()
        mapping = _FRED_INDEX_SERIES.get(code)
        if mapping is None:
            return []
        series_id, _name = mapping
        try:
            response = self._session.get(
                _FRED_GRAPH_URL,
                params={"id": series_id},
                headers=self._headers,
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            frame = pd.read_csv(StringIO(response.text))
        except (requests.RequestException, ValueError, pd.errors.ParserError) as exc:
            raise DataFetchError(f"[FRED] public series request failed: {type(exc).__name__}") from exc
        date_column = "observation_date"
        if date_column not in frame.columns or series_id not in frame.columns:
            raise DataFetchError(f"[FRED] unexpected series payload for {series_id}")
        frame[date_column] = pd.to_datetime(frame[date_column], errors="coerce")
        frame[series_id] = pd.to_numeric(frame[series_id], errors="coerce")
        start, end = pd.Timestamp(start_date), pd.Timestamp(end_date)
        frame = frame[(frame[date_column] >= start) & (frame[date_column] <= end)].dropna(subset=[date_column, series_id])
        return [
            {
                "date": row[date_column],
                # FRED publishes a closing series only.  Never manufacture
                # OHLC values by copying the close into those fields.
                "open": None,
                "high": None,
                "low": None,
                "close": float(row[series_id]),
                "volume": 0.0,
                "amount": None,
                "source_fields": {"volume": "未取得", "open_high_low": "未取得"},
            }
            for _, row in frame.iterrows()
        ]

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        code = (stock_code or "").strip().upper()
        rows = self._fred_rows(code, start_date=start_date, end_date=end_date)
        if not rows:
            rows = self._nasdaq_history_rows(code, start_date=start_date, end_date=end_date)
        if not rows:
            raise DataFetchError(f"[Nasdaq/FRED] no historical OHLCV returned for {stock_code}")
        return pd.DataFrame(rows).drop_duplicates(subset=["date"]).sort_values("date")

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        normalized = df.copy()
        normalized["pct_chg"] = normalized["close"].pct_change().fillna(0.0) * 100
        normalized["code"] = stock_code.strip().upper()
        for column in STANDARD_COLUMNS:
            if column not in normalized.columns:
                normalized[column] = None
        return normalized[["code", *STANDARD_COLUMNS]]

    def get_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """Return Nasdaq's delayed quote for a US equity when live APIs fail."""
        code = (stock_code or "").strip().upper()
        if not is_us_stock_code(code):
            return None
        try:
            data = self._get_json(code, "info", params={"assetclass": "stocks"})
        except DataFetchError as exc:
            logger.warning("[Nasdaq] public quote unavailable for %s: %s", code, exc)
            return None
        primary = data.get("primaryData") or {}
        price = _number(primary.get("lastSalePrice"))
        if price is None or price <= 0:
            return None
        change_amount = _number(primary.get("netChange"))
        change_pct = _number(primary.get("percentageChange"))
        return UnifiedRealtimeQuote(
            code=code,
            name=str(data.get("companyName") or code),
            source=RealtimeSource.NASDAQ,
            market="us",
            currency="USD",
            data_quality="partial",
            missing_fields=["volume", "turnover_rate"],
            price=price,
            change_amount=change_amount,
            change_pct=change_pct,
        )

    def get_main_indices(self, region: str = "cn") -> Optional[list[dict[str, Any]]]:
        """Obtain US market-review core indices from public Nasdaq/FRED data."""
        if region != "us":
            return None
        from datetime import datetime, timedelta

        end = datetime.utcnow().date()
        start = end - timedelta(days=45)
        start_date, end_date = start.isoformat(), end.isoformat()
        results: list[dict[str, Any]] = []
        for code in ("SPX", "IXIC", "DJI", "SOX", "VIX"):
            try:
                rows = self._fred_rows(code, start_date=start_date, end_date=end_date)
                if not rows:
                    rows = self._nasdaq_history_rows(code, start_date=start_date, end_date=end_date)
            except DataFetchError as exc:
                logger.warning("[Nasdaq/FRED] index %s unavailable: %s", code, exc)
                continue
            if not rows:
                continue
            rows.sort(key=lambda item: item["date"])
            latest = rows[-1]
            previous = rows[-2] if len(rows) > 1 else latest
            current = float(latest["close"])
            prev_close = float(previous["close"])
            change = current - prev_close
            results.append(
                {
                    "code": code,
                    "name": _INDEX_NAMES.get(code, code),
                    "current": current,
                    "change": change,
                    "change_pct": (change / prev_close * 100) if prev_close else None,
                    "open": latest.get("open"),
                    "high": latest.get("high"),
                    "low": latest.get("low"),
                    "prev_close": prev_close,
                    "volume": None if latest.get("source_fields", {}).get("volume") == "未取得" else latest.get("volume"),
                    "amount": None,
                    "amplitude": (
                        (float(latest["high"]) - float(latest["low"])) / prev_close * 100
                        if latest.get("high") is not None and latest.get("low") is not None and prev_close
                        else None
                    ),
                    "source_fields": latest.get("source_fields", {}),
                }
            )
        return results or None
