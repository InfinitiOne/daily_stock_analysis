# -*- coding: utf-8 -*-
"""FinMind REST provider for Taiwan daily market data.

FinMind is a Taiwan-data complement. It is used for end-of-day OHLCV only;
Fugle remains the preferred provider for Taiwan intraday quotes.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Mapping, Optional

import pandas as pd
import requests

from src.services.market_symbol_utils import is_suffix_market_symbol
from .base import BaseFetcher, DataFetchError, STANDARD_COLUMNS

logger = logging.getLogger(__name__)

_FINMIND_BASE_URL = "https://api.finmindtrade.com/api/v4"


def _env_number(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


class FinMindFetcher(BaseFetcher):
    """Fetch Taiwan daily OHLCV from the official FinMind REST API."""

    name = "FinMindFetcher"
    priority = 1

    def __init__(
        self,
        api_token: Optional[str] = None,
        priority: Optional[int] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        self._api_token = (
            api_token if api_token is not None else os.getenv("FINMIND_API_TOKEN", "")
        ).strip()
        self.priority = int(priority if priority is not None else _env_number("FINMIND_PRIORITY", 1))
        self._timeout_seconds = max(1.0, _env_number("FINMIND_TIMEOUT_SECONDS", 12.0))
        self._session = session or requests.Session()

    def is_available(self, capability: str = "") -> bool:
        return bool(self._api_token)

    @staticmethod
    def _stock_id(stock_code: str) -> str:
        code = (stock_code or "").strip().upper()
        if not is_suffix_market_symbol(code, "tw"):
            raise DataFetchError(f"[FinMind] {stock_code} is not a Taiwan .TW/.TWO symbol")
        return code.rsplit(".", 1)[0]

    def _get_dataset(
        self,
        dataset: str,
        *,
        data_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        if not self._api_token:
            raise DataFetchError("[FinMind] API token is not configured")

        params: dict[str, Any] = {"dataset": dataset}
        if data_id:
            params["data_id"] = data_id
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        try:
            response = self._session.get(
                f"{_FINMIND_BASE_URL}/data",
                headers={"Authorization": f"Bearer {self._api_token}"},
                params=params,
                timeout=self._timeout_seconds,
            )
        except requests.RequestException as exc:
            raise DataFetchError(f"[FinMind] request failed: {type(exc).__name__}") from exc

        if response.status_code == 402:
            raise DataFetchError("[FinMind] API quota or plan limit reached")
        if response.status_code in (401, 403):
            raise DataFetchError("[FinMind] authentication was rejected")
        try:
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise DataFetchError(f"[FinMind] invalid API response: {type(exc).__name__}") from exc

        if not isinstance(payload, Mapping) or int(payload.get("status", 200)) != 200:
            raise DataFetchError("[FinMind] API returned an unsuccessful response")
        rows = payload.get("data", [])
        if not isinstance(rows, list):
            raise DataFetchError("[FinMind] API data field has an unexpected format")
        return rows

    def get_dataset(
        self,
        dataset: str,
        stock_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """Return a documented FinMind Taiwan dataset for future report adapters."""
        return pd.DataFrame(
            self._get_dataset(
                dataset,
                data_id=self._stock_id(stock_code),
                start_date=start_date,
                end_date=end_date,
            )
        )

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        stock_id = self._stock_id(stock_code)
        rows = self._get_dataset(
            "TaiwanStockPrice",
            data_id=stock_id,
            start_date=start_date,
            end_date=end_date,
        )
        if not rows:
            raise DataFetchError(f"[FinMind] no TaiwanStockPrice rows returned for {stock_id}")
        return pd.DataFrame(rows)

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        normalized = df.copy()
        required = {"date", "open", "max", "min", "close", "Trading_Volume", "Trading_money"}
        missing = required.difference(normalized.columns)
        if missing:
            raise DataFetchError(
                f"[FinMind] TaiwanStockPrice missing fields: {', '.join(sorted(missing))}"
            )

        normalized = normalized.rename(
            columns={
                "max": "high",
                "min": "low",
                "Trading_Volume": "volume",
                "Trading_money": "amount",
            }
        )
        if "spread" in normalized.columns:
            previous_close = normalized["close"] - normalized["spread"]
            normalized["pct_chg"] = (
                normalized["spread"] / previous_close.replace(0, pd.NA) * 100
            )
        else:
            normalized["pct_chg"] = normalized["close"].pct_change() * 100
        normalized["pct_chg"] = normalized["pct_chg"].fillna(0)
        normalized["code"] = stock_code.strip().upper()
        keep = ["code", *STANDARD_COLUMNS]
        return normalized[[column for column in keep if column in normalized.columns]]
