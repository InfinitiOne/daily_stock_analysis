# -*- coding: utf-8 -*-
"""Official TWSE / TPEx historical daily-price fallback for Taiwan securities.

This is deliberately a *last-resort* public-web route.  It is used after the
configured commercial/API providers and Yahoo Finance, so a temporary provider
outage does not turn a valid Taiwan holding into a fabricated 0-score or sell
signal.  The endpoints are published by TWSE and TPEx and require no token.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime
from typing import Any, Iterable, Optional

import pandas as pd
import requests

from src.services.market_symbol_utils import is_suffix_market_symbol
from .base import BaseFetcher, DataFetchError, STANDARD_COLUMNS
from .realtime_types import RealtimeSource, UnifiedRealtimeQuote


logger = logging.getLogger(__name__)

_TWSE_STOCK_DAY = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"
_TPEX_MONTHLY = "https://www.tpex.org.tw/web/stock/aftertrading/daily_trading_info/st43_result.php"
_TWSE_OPEN_API = "https://openapi.twse.com.tw/v1"
_TPEX_OPEN_API = "https://www.tpex.org.tw/openapi/v1"


def _env_number(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _number(value: Any) -> Optional[float]:
    text = str(value or "").replace(",", "").replace(" ", "").strip()
    if text in {"", "--", "---", "-", "X"}:
        return None
    text = text.replace("+", "")
    try:
        return float(text)
    except ValueError:
        return None


def _roc_date(value: Any) -> Optional[pd.Timestamp]:
    text = str(value or "").strip().replace("-", "/")
    parts = text.split("/")
    if len(parts) != 3:
        return None
    try:
        year = int(parts[0]) + 1911 if int(parts[0]) < 1911 else int(parts[0])
        return pd.Timestamp(year=year, month=int(parts[1]), day=int(parts[2]))
    except (TypeError, ValueError):
        return None


def _month_starts(start: str, end: str) -> Iterable[date]:
    cursor = datetime.strptime(start, "%Y-%m-%d").date().replace(day=1)
    last = datetime.strptime(end, "%Y-%m-%d").date().replace(day=1)
    while cursor <= last:
        yield cursor
        cursor = date(cursor.year + (cursor.month == 12), (cursor.month % 12) + 1, 1)


class TwseTpexFetcher(BaseFetcher):
    """No-key official-exchange fallback for `.TW` and `.TWO` daily OHLCV."""

    name = "TwseTpexFetcher"
    priority = 8

    def __init__(self, session: Optional[requests.Session] = None, priority: Optional[int] = None) -> None:
        self.priority = int(priority if priority is not None else _env_number("TWSE_TPEX_PRIORITY", 8))
        self._timeout_seconds = max(2.0, _env_number("TWSE_TPEX_TIMEOUT_SECONDS", 15.0))
        self._throttle_seconds = max(0.0, _env_number("TWSE_TPEX_THROTTLE_SECONDS", 0.35))
        self._session = session or requests.Session()
        self._headers = {
            "User-Agent": "JEAC-Enterprise/5.0 contact: repository-owner",
            "Accept": "application/json,text/plain,*/*",
        }

    def is_available(self, capability: str = "") -> bool:
        return True

    @staticmethod
    def _split_symbol(stock_code: str) -> tuple[str, str]:
        code = (stock_code or "").strip().upper()
        if not is_suffix_market_symbol(code, "tw"):
            raise DataFetchError(f"[TWSE/TPEx] {stock_code} is not a supported Taiwan .TW/.TWO symbol")
        base, suffix = code.rsplit(".", 1)
        return base, suffix

    def _get_json(self, url: str, *, params: dict[str, Any]) -> dict[str, Any]:
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
            raise DataFetchError(f"[TWSE/TPEx] official endpoint request failed: {type(exc).__name__}") from exc
        if not isinstance(payload, dict):
            raise DataFetchError("[TWSE/TPEx] official endpoint returned an unexpected payload")
        return payload

    def _get_json_or_list(self, url: str, *, params: Optional[dict[str, Any]] = None) -> Any:
        """Fetch a public official endpoint whose top-level JSON can be a list."""
        try:
            response = self._session.get(
                url,
                params=params or {},
                headers=self._headers,
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            raise DataFetchError(f"[TWSE/TPEx] official endpoint request failed: {type(exc).__name__}") from exc

    @staticmethod
    def _official_quote_number(value: Any) -> Optional[float]:
        return _number(value)

    def _official_latest_quote_row(self, stock_code: str) -> Optional[dict[str, Any]]:
        """Return the latest official closing row for a Taiwan stock or ETF."""
        base, suffix = self._split_symbol(stock_code)
        if suffix == "TW":
            rows = self._get_json_or_list(f"{_TWSE_OPEN_API}/exchangeReport/STOCK_DAY_ALL")
            if not isinstance(rows, list):
                return None
            for row in rows:
                if isinstance(row, dict) and str(row.get("Code") or "").strip().upper() == base:
                    return {
                        "date": row.get("Date"),
                        "name": row.get("Name"),
                        "close": row.get("ClosingPrice"),
                        "change": row.get("Change"),
                        "open": row.get("OpeningPrice"),
                        "high": row.get("HighestPrice"),
                        "low": row.get("LowestPrice"),
                        "volume": row.get("TradeVolume"),
                        "amount": row.get("TradeValue"),
                    }
            return None

        rows = self._get_json_or_list(f"{_TPEX_OPEN_API}/tpex_mainboard_daily_close_quotes")
        if not isinstance(rows, list):
            return None
        for row in rows:
            if isinstance(row, dict) and str(row.get("SecuritiesCompanyCode") or "").strip().upper() == base:
                return {
                    "date": row.get("Date"),
                    "name": row.get("CompanyName"),
                    "close": row.get("Close"),
                    "change": row.get("Change"),
                    "open": row.get("Open"),
                    "high": row.get("High"),
                    "low": row.get("Low"),
                    "volume": row.get("TradingShares"),
                    "amount": row.get("TransactionAmount"),
                }
        return None

    def get_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """Use official end-of-day data when Taiwan quote APIs are unavailable.

        The exchange endpoints are not an intraday feed.  The quote therefore
        carries a clear ``partial`` quality marker instead of pretending to be
        real-time.
        """
        try:
            row = self._official_latest_quote_row(stock_code)
        except DataFetchError as exc:
            logger.warning("[TWSE/TPEx] official quote unavailable for %s: %s", stock_code, exc)
            return None
        if not row:
            return None
        price = self._official_quote_number(row.get("close"))
        if price is None or price <= 0:
            return None
        change_amount = self._official_quote_number(row.get("change"))
        previous_close = price - change_amount if change_amount is not None else None
        change_pct = (change_amount / previous_close * 100) if previous_close else None
        return UnifiedRealtimeQuote(
            code=stock_code.strip().upper(),
            name=str(row.get("name") or stock_code),
            source=RealtimeSource.TWSE_TPEX,
            market="tw",
            currency="TWD",
            data_quality="partial",
            missing_fields=["turnover_rate", "volume_ratio"],
            price=price,
            change_amount=change_amount,
            change_pct=change_pct,
            volume=int(self._official_quote_number(row.get("volume")) or 0) or None,
            amount=self._official_quote_number(row.get("amount")),
            open_price=self._official_quote_number(row.get("open")),
            high=self._official_quote_number(row.get("high")),
            low=self._official_quote_number(row.get("low")),
            pre_close=previous_close,
        )

    def get_main_indices(self, region: str = "cn") -> Optional[list[dict[str, Any]]]:
        """Return Taiwan core indices directly from TWSE and TPEx OpenAPI."""
        if region != "tw":
            return None
        # Do not make the two official exchanges a single point of failure.
        # The caller can still merge the available official index with its
        # next public fallback when either endpoint is temporarily down.
        try:
            twse_rows = self._get_json_or_list(f"{_TWSE_OPEN_API}/exchangeReport/MI_INDEX")
        except DataFetchError as exc:
            logger.warning("[TWSE] official index endpoint unavailable: %s", exc)
            twse_rows = None
        try:
            tpex_rows = self._get_json_or_list(f"{_TPEX_OPEN_API}/tpex_index")
        except DataFetchError as exc:
            logger.warning("[TPEx] official index endpoint unavailable: %s", exc)
            tpex_rows = None

        result: list[dict[str, Any]] = []
        if isinstance(twse_rows, list):
            target = next(
                (
                    row for row in twse_rows
                    if isinstance(row, dict) and str(row.get("指數") or "").strip() == "發行量加權股價指數"
                ),
                None,
            )
            if target:
                current = _number(target.get("收盤指數"))
                change = _number(target.get("漲跌點數"))
                change_pct = _number(target.get("漲跌百分比"))
                sign = str(target.get("漲跌") or "").strip()
                if sign in {"-", "－", "跌"}:
                    change = -abs(change) if change is not None else None
                    change_pct = -abs(change_pct) if change_pct is not None else None
                if current is not None:
                    result.append(
                        {
                            "code": "TWII",
                            "name": "臺灣加權指數",
                            "current": current,
                            "change": change,
                            "change_pct": change_pct,
                            "open": None,
                            "high": None,
                            "low": None,
                            "prev_close": current - change if change is not None else None,
                            "volume": None,
                            "amount": None,
                            "amplitude": None,
                            "source_fields": {"open_high_low": "未取得", "volume": "未取得", "amount": "未取得"},
                        }
                    )

        if isinstance(tpex_rows, list):
            parsed: list[dict[str, Any]] = []
            for row in tpex_rows:
                if not isinstance(row, dict):
                    continue
                current = _number(row.get("Close"))
                when = pd.to_datetime(row.get("Date"), errors="coerce")
                if current is None or pd.isna(when):
                    continue
                parsed.append({"date": when, "row": row, "close": current})
            parsed.sort(key=lambda item: item["date"])
            if parsed:
                latest = parsed[-1]
                previous = parsed[-2] if len(parsed) > 1 else latest
                row = latest["row"]
                current = latest["close"]
                prev_close = previous["close"]
                change = _number(row.get("Change"))
                result.append(
                    {
                        "code": "TWOII",
                        "name": "櫃買指數",
                        "current": current,
                        "change": change if change is not None else current - prev_close,
                        "change_pct": ((current - prev_close) / prev_close * 100) if prev_close else None,
                        "open": _number(row.get("Open")),
                        "high": _number(row.get("High")),
                        "low": _number(row.get("Low")),
                        "prev_close": prev_close,
                        "volume": None,
                        "amount": None,
                        "amplitude": None,
                        "source_fields": {"volume": "未取得", "amount": "未取得"},
                    }
                )
        return result or None

    def _fetch_twse_month(self, base: str, month: date) -> list[dict[str, Any]]:
        payload = self._get_json(
            _TWSE_STOCK_DAY,
            params={"response": "json", "date": month.strftime("%Y%m%d"), "stockNo": base},
        )
        rows = payload.get("data") or []
        if not isinstance(rows, list):
            return []
        parsed: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, list) or len(row) < 9:
                continue
            row_date = _roc_date(row[0])
            open_, high, low, close = (_number(row[index]) for index in (3, 4, 5, 6))
            volume, amount = _number(row[1]), _number(row[2])
            if row_date is None or None in {open_, high, low, close, volume}:
                continue
            parsed.append({
                "date": row_date,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
                "amount": amount or 0.0,
            })
        return parsed

    def _fetch_tpex_month(self, base: str, month: date) -> list[dict[str, Any]]:
        roc_month = f"{month.year - 1911}/{month.month:02d}"
        payload = self._get_json(
            _TPEX_MONTHLY,
            params={"l": "zh-tw", "d": roc_month, "stkno": base},
        )
        rows = payload.get("aaData") or payload.get("data") or []
        if not isinstance(rows, list):
            return []
        parsed: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, list) or len(row) < 10:
                continue
            row_date = _roc_date(row[0])
            # TPEx st43 monthly columns: date, code, name, close, change,
            # open, high, low, average, volume, amount, transactions, ...
            close, open_, high, low = (_number(row[index]) for index in (3, 5, 6, 7))
            volume = _number(row[9])
            amount = _number(row[10]) if len(row) > 10 else None
            if row_date is None or None in {open_, high, low, close, volume}:
                continue
            parsed.append({
                "date": row_date,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
                "amount": amount or 0.0,
            })
        return parsed

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        base, suffix = self._split_symbol(stock_code)
        fetch_month = self._fetch_twse_month if suffix == "TW" else self._fetch_tpex_month
        rows: list[dict[str, Any]] = []
        failures: list[str] = []
        for month in _month_starts(start_date, end_date):
            try:
                rows.extend(fetch_month(base, month))
            except DataFetchError as exc:
                failures.append(str(exc))
            if self._throttle_seconds:
                time.sleep(self._throttle_seconds)
        if not rows:
            detail = failures[-1] if failures else "no rows returned"
            raise DataFetchError(f"[TWSE/TPEx] no official historical rows for {stock_code}: {detail}")
        df = pd.DataFrame(rows).drop_duplicates(subset=["date"]).sort_values("date")
        start_ts, end_ts = pd.Timestamp(start_date), pd.Timestamp(end_date)
        return df[(df["date"] >= start_ts) & (df["date"] <= end_ts)].reset_index(drop=True)

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        normalized = df.copy()
        previous_close = normalized["close"].shift(1)
        normalized["pct_chg"] = (normalized["close"] - previous_close) / previous_close.replace(0, pd.NA) * 100
        normalized["pct_chg"] = normalized["pct_chg"].fillna(0.0)
        normalized["code"] = stock_code.strip().upper()
        return normalized[["code", *STANDARD_COLUMNS]]
