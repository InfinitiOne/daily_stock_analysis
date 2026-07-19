# -*- coding: utf-8 -*-
"""Public SEC EDGAR fallback for US-company fundamentals.

The adapter deliberately uses only SEC-published company facts.  It is called
after the existing fundamental adapter returns no meaningful US growth or
earnings evidence, and it reports an explicit failure reason instead of
inventing financial values.
"""

from __future__ import annotations

import logging
import os
import time
from threading import RLock
from typing import Any, Iterable, Optional

import requests

from .us_index_mapping import is_us_stock_code


logger = logging.getLogger(__name__)

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
_REVENUE_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
    "Revenues",
)
_NET_INCOME_TAGS = ("NetIncomeLoss",)
_OPERATING_CASH_FLOW_TAGS = ("NetCashProvidedByUsedInOperatingActivities",)


def _numeric(value: Any) -> Optional[float]:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if numeric == numeric else None  # NaN guard


class SecEdgarFundamentalAdapter:
    """No-key SEC company-facts fallback for US equity fundamentals."""

    name = "SEC EDGAR Company Facts"
    _cache_lock = RLock()
    _ticker_cache: Optional[tuple[float, dict[str, int]]] = None
    _facts_cache: dict[int, tuple[float, dict[str, Any]]] = {}

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self._session = session or requests.Session()
        try:
            self._timeout_seconds = max(2.0, float(os.getenv("SEC_EDGAR_TIMEOUT_SECONDS", "15")))
        except ValueError:
            self._timeout_seconds = 15.0
        try:
            self._cache_ttl_seconds = max(300.0, float(os.getenv("SEC_EDGAR_CACHE_TTL_SECONDS", "86400")))
        except ValueError:
            self._cache_ttl_seconds = 86400.0
        contact = os.getenv("SEC_USER_AGENT", "").strip()
        # SEC asks automated clients to identify themselves.  This default is
        # conservative and callers can set SEC_USER_AGENT to their contact.
        self._headers = {
            "User-Agent": contact or "JEAC-Enterprise/5.0 research contact: repository-owner",
            "Accept-Encoding": "gzip, deflate",
            "Accept": "application/json",
        }

    def _get_json(self, url: str) -> Any:
        try:
            response = self._session.get(url, headers=self._headers, timeout=self._timeout_seconds)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            raise RuntimeError(f"SEC EDGAR request failed: {type(exc).__name__}") from exc

    def _ticker_map(self) -> dict[str, int]:
        with self._cache_lock:
            cached = self._ticker_cache
            if cached and time.time() - cached[0] <= self._cache_ttl_seconds:
                return cached[1]
        payload = self._get_json(_TICKERS_URL)
        if not isinstance(payload, dict):
            raise RuntimeError("SEC EDGAR ticker map returned unexpected payload")
        mapping: dict[str, int] = {}
        for item in payload.values():
            if not isinstance(item, dict):
                continue
            ticker = str(item.get("ticker") or "").strip().upper()
            cik = item.get("cik_str")
            try:
                cik_value = int(cik)
            except (TypeError, ValueError):
                continue
            if ticker:
                mapping[ticker] = cik_value
        with self._cache_lock:
            self._ticker_cache = (time.time(), mapping)
        return mapping

    def _facts(self, cik: int) -> dict[str, Any]:
        with self._cache_lock:
            cached = self._facts_cache.get(cik)
            if cached and time.time() - cached[0] <= self._cache_ttl_seconds:
                return cached[1]
        payload = self._get_json(_COMPANY_FACTS_URL.format(cik=cik))
        if not isinstance(payload, dict):
            raise RuntimeError("SEC EDGAR company facts returned unexpected payload")
        with self._cache_lock:
            self._facts_cache[cik] = (time.time(), payload)
        return payload

    @staticmethod
    def _facts_for_tags(payload: dict[str, Any], tags: Iterable[str]) -> list[dict[str, Any]]:
        us_gaap = payload.get("facts", {}).get("us-gaap", {}) if isinstance(payload.get("facts"), dict) else {}
        for tag in tags:
            node = us_gaap.get(tag)
            units = node.get("units") if isinstance(node, dict) else None
            if not isinstance(units, dict):
                continue
            values = units.get("USD")
            if not isinstance(values, list):
                continue
            usable = [
                item
                for item in values
                if isinstance(item, dict)
                and _numeric(item.get("val")) is not None
                and str(item.get("form") or "") in {"10-K", "10-Q"}
                and str(item.get("end") or "")
            ]
            if usable:
                return usable
        return []

    @staticmethod
    def _latest(values: list[dict[str, Any]], *, annual_only: bool = False) -> Optional[dict[str, Any]]:
        filtered = list(values)
        if annual_only:
            annual = [item for item in filtered if str(item.get("fp") or "") == "FY"]
            if annual:
                filtered = annual
        if not filtered:
            return None
        return max(
            filtered,
            key=lambda item: (
                str(item.get("filed") or ""),
                str(item.get("end") or ""),
                str(item.get("accn") or ""),
            ),
        )

    @classmethod
    def _annual_yoy(cls, values: list[dict[str, Any]]) -> Optional[float]:
        annual = [item for item in values if str(item.get("fp") or "") == "FY"]
        # Use one most recently filed value per fiscal-year end.
        by_end: dict[str, dict[str, Any]] = {}
        for item in annual:
            end = str(item.get("end") or "")
            if not end:
                continue
            current = by_end.get(end)
            if current is None or str(item.get("filed") or "") > str(current.get("filed") or ""):
                by_end[end] = item
        ordered = sorted(by_end.values(), key=lambda item: str(item.get("end") or ""))
        if len(ordered) < 2:
            return None
        current, previous = ordered[-1], ordered[-2]
        current_value = _numeric(current.get("val"))
        previous_value = _numeric(previous.get("val"))
        if current_value is None or previous_value in (None, 0):
            return None
        return round((current_value / previous_value - 1.0) * 100.0, 4)

    def get_fundamental_bundle(self, stock_code: str) -> dict[str, Any]:
        result: dict[str, Any] = {
            "status": "not_supported",
            "growth": {},
            "earnings": {},
            "belong_boards": [],
            "source_chain": [],
            "errors": [],
        }
        code = str(stock_code or "").strip().upper()
        if not is_us_stock_code(code):
            result["errors"].append("SEC EDGAR 僅支援美股代碼")
            return result

        started = time.monotonic()
        try:
            cik = self._ticker_map().get(code)
            if cik is None:
                raise RuntimeError("SEC EDGAR 找不到此代碼的 CIK")
            facts = self._facts(cik)
        except RuntimeError as exc:
            result["errors"].append(str(exc))
            result["source_chain"] = [
                {"provider": self.name, "result": "failed", "duration_ms": int((time.monotonic() - started) * 1000)}
            ]
            return result

        revenue_values = self._facts_for_tags(facts, _REVENUE_TAGS)
        net_income_values = self._facts_for_tags(facts, _NET_INCOME_TAGS)
        operating_cash_values = self._facts_for_tags(facts, _OPERATING_CASH_FLOW_TAGS)
        revenue_latest = self._latest(revenue_values, annual_only=True) or self._latest(revenue_values)
        net_income_latest = self._latest(net_income_values, annual_only=True) or self._latest(net_income_values)
        cash_latest = self._latest(operating_cash_values, annual_only=True) or self._latest(operating_cash_values)

        growth = {
            "revenue_yoy": self._annual_yoy(revenue_values),
            "net_income_yoy": self._annual_yoy(net_income_values),
        }
        growth = {key: value for key, value in growth.items() if value is not None}
        financial_report = {
            "report_date": str((revenue_latest or net_income_latest or {}).get("end") or "") or None,
            "revenue": _numeric((revenue_latest or {}).get("val")),
            "net_income_loss": _numeric((net_income_latest or {}).get("val")),
            "operating_cash_flow": _numeric((cash_latest or {}).get("val")),
            "currency": "USD",
            "source_form": str((revenue_latest or net_income_latest or {}).get("form") or "") or None,
            "filed_date": str((revenue_latest or net_income_latest or {}).get("filed") or "") or None,
        }
        financial_report = {key: value for key, value in financial_report.items() if value is not None}
        if growth:
            result["growth"] = growth
        # Filing dates and a currency alone are evidence of a request, not a
        # usable fundamental figure.  Keep the result unavailable unless at
        # least one reported financial amount is present.
        has_financial_amount = any(
            financial_report.get(key) is not None
            for key in ("revenue", "net_income_loss", "operating_cash_flow")
        )
        if has_financial_amount:
            result["earnings"] = {"financial_report": financial_report}
        has_content = bool(growth or has_financial_amount)
        result["status"] = "partial" if has_content else "not_supported"
        result["source_chain"] = [
            {
                "provider": self.name,
                "result": "ok" if has_content else "empty",
                "duration_ms": int((time.monotonic() - started) * 1000),
            }
        ]
        if not has_content:
            result["errors"].append("SEC EDGAR 沒有可用的 10-K／10-Q 公司事實欄位")
        return result
