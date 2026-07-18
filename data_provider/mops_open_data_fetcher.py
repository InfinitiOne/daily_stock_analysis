# -*- coding: utf-8 -*-
"""Public MOPS Open Data fallback for Taiwan-company fundamentals.

This adapter reads the official MOPS datasets mirrored on the TWSE OpenAPI
service.  It is intentionally additive: it fills monthly-revenue and basic
quarterly financial fields when FinMind/Yahoo-style adapters do not return
them.  It never turns a failed request into a numeric zero.
"""

from __future__ import annotations

import logging
import os
import time
from threading import RLock
from typing import Any, Optional

import requests

from src.services.market_symbol_utils import is_tw_etf_symbol, split_suffix_symbol


logger = logging.getLogger(__name__)

_OPENAPI_ROOT = "https://openapi.twse.com.tw/v1/opendata"
_MONTHLY_REVENUE_DATASET = "t187ap05"
_QUARTERLY_FINANCIAL_DATASET = "t187ap14"
_BOARD_BY_SUFFIX = {"TW": "L", "TWO": "O"}


def _number(value: Any) -> Optional[float]:
    text = str(value or "").strip().replace(",", "").replace("%", "")
    if text in {"", "-", "--", "---", "N/A", "None"}:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


class MopsOpenDataFetcher:
    """No-key official Taiwan monthly-revenue / financial-data fallback."""

    name = "MopsOpenDataFetcher"
    _cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
    _cache_lock = RLock()

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self._session = session or requests.Session()
        try:
            self._timeout_seconds = max(2.0, float(os.getenv("MOPS_OPEN_DATA_TIMEOUT_SECONDS", "15")))
        except ValueError:
            self._timeout_seconds = 15.0
        try:
            self._cache_ttl_seconds = max(60.0, float(os.getenv("MOPS_OPEN_DATA_CACHE_TTL_SECONDS", "900")))
        except ValueError:
            self._cache_ttl_seconds = 900.0
        self._headers = {
            "User-Agent": "JEAC-Enterprise/5.0 public-data research",
            "Accept": "application/json,text/plain,*/*",
        }

    @staticmethod
    def _symbol_parts(stock_code: str) -> tuple[str, str]:
        parts = split_suffix_symbol(stock_code)
        if parts is None:
            raise ValueError("臺股代碼必須使用 .TW 或 .TWO 字尾")
        code, suffix = parts
        board = _BOARD_BY_SUFFIX.get(suffix)
        if board is None or not code:
            raise ValueError("臺股代碼必須使用 .TW 或 .TWO 字尾")
        return code, board

    def _rows(self, dataset: str, board: str) -> list[dict[str, Any]]:
        cache_key = f"{dataset}_{board}"
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached and time.time() - cached[0] <= self._cache_ttl_seconds:
                return cached[1]

        url = f"{_OPENAPI_ROOT}/{dataset}_{board}"
        try:
            response = self._session.get(url, headers=self._headers, timeout=self._timeout_seconds)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise RuntimeError(f"{dataset}_{board}: {type(exc).__name__}") from exc
        if not isinstance(payload, list):
            raise RuntimeError(f"{dataset}_{board}: unexpected payload")
        rows = [row for row in payload if isinstance(row, dict)]
        with self._cache_lock:
            self._cache[cache_key] = (time.time(), rows)
        return rows

    @staticmethod
    def _match(rows: list[dict[str, Any]], code: str) -> Optional[dict[str, Any]]:
        return next(
            (
                row
                for row in rows
                if str(row.get("公司代號") or "").strip().upper() == code.upper()
            ),
            None,
        )

    def get_fundamental_bundle(self, stock_code: str) -> dict[str, Any]:
        """Return official monthly-revenue and quarterly-financial evidence.

        ETF issuers do not have comparable operating revenue / earnings, so the
        result says so explicitly rather than submitting an inapplicable value.
        """

        if is_tw_etf_symbol(stock_code):
            return {
                "status": "not_supported",
                "growth": {},
                "earnings": {},
                "belong_boards": [],
                "source_chain": [
                    {"provider": self.name, "result": "not_supported", "duration_ms": 0}
                ],
                "errors": ["ETF 不適用公司月營收與財報欄位"],
            }

        started = time.monotonic()
        result: dict[str, Any] = {
            "status": "not_supported",
            "growth": {},
            "earnings": {},
            "belong_boards": [],
            "source_chain": [],
            "errors": [],
        }
        try:
            code, board = self._symbol_parts(stock_code)
        except ValueError as exc:
            result["errors"].append(str(exc))
            return result

        monthly_row = None
        financial_row = None
        for dataset, target in (
            (_MONTHLY_REVENUE_DATASET, "monthly"),
            (_QUARTERLY_FINANCIAL_DATASET, "financial"),
        ):
            try:
                row = self._match(self._rows(dataset, board), code)
            except RuntimeError as exc:
                result["errors"].append(str(exc))
                continue
            if target == "monthly":
                monthly_row = row
            else:
                financial_row = row

        duration_ms = int((time.monotonic() - started) * 1000)
        if monthly_row:
            monthly_revenue = {
                "period_roc": str(monthly_row.get("資料年月") or "").strip() or None,
                "monthly_revenue": _number(monthly_row.get("營業收入-當月營收")),
                "monthly_revenue_mom_pct": _number(monthly_row.get("營業收入-上月比較增減(%)")),
                "monthly_revenue_yoy_pct": _number(monthly_row.get("營業收入-去年同月增減(%)")),
                "cumulative_revenue_yoy_pct": _number(monthly_row.get("累計營業收入-前期比較增減(%)")),
                "currency": "TWD",
            }
            # A row can exist before all quantitative fields have been filed.
            # Do not describe that as a usable revenue result merely because
            # the dataset supplied its currency / period metadata.
            if any(
                monthly_revenue.get(key) is not None
                for key in (
                    "monthly_revenue",
                    "monthly_revenue_mom_pct",
                    "monthly_revenue_yoy_pct",
                    "cumulative_revenue_yoy_pct",
                )
            ):
                result["growth"] = {"monthly_revenue": monthly_revenue}

        if financial_row:
            year = str(financial_row.get("年度") or "").strip()
            quarter = str(financial_row.get("季別") or "").strip()
            financial_report = {
                "period_roc": f"{year}Q{quarter}" if year and quarter else None,
                "revenue": _number(financial_row.get("營業收入")),
                # MOPS t187ap14 publishes after-tax net profit, not an
                # attributable-to-parent field; retain the official label.
                "net_profit_after_tax": _number(financial_row.get("稅後淨利")),
                "operating_profit": _number(financial_row.get("營業利益")),
                "basic_eps": _number(financial_row.get("基本每股盈餘(元)")),
                "currency": "TWD",
            }
            if any(
                financial_report.get(key) is not None
                for key in ("revenue", "net_profit_after_tax", "operating_profit", "basic_eps")
            ):
                result["earnings"] = {"financial_report": financial_report}

        industry = str((monthly_row or financial_row or {}).get("產業別") or "").strip()
        if industry and industry not in {"-", "－"}:
            result["belong_boards"] = [{"name": industry, "type": "產業"}]

        has_content = bool(result["growth"] or result["earnings"] or result["belong_boards"])
        result["status"] = "partial" if has_content else "not_supported"
        result["source_chain"] = [
            {
                "provider": "MOPS Open Data（TWSE OpenAPI）",
                "result": "ok" if has_content else "empty",
                "duration_ms": duration_ms,
            }
        ]
        if not has_content and not result["errors"]:
            result["errors"].append("MOPS Open Data 未找到該公司資料")
        return result
