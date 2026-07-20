"""Guardrails for reusing a completed JEAC run on the same Taipei date.

The GitHub-hosted runner is ephemeral, so the workflows persist the SQLite
state with an Actions cache.  This module keeps the cache contract explicit:
only records written by the same report kind/date and marked with the current
schema are eligible.  Missing, partial, or provider-failure records are never
treated as a cache hit.
"""

from __future__ import annotations

import os
import hashlib
import json
from datetime import date, datetime, timezone
from typing import Any, Dict, Mapping, Optional
from zoneinfo import ZoneInfo


SAME_DAY_REUSE_SCHEMA_VERSION = 1
TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def same_day_reuse_enabled() -> bool:
    """Return whether workflow-scoped same-day reuse is enabled."""

    return _env_bool("JEAC_SAME_DAY_REUSE_ENABLED", False)


def report_kind() -> str:
    """Return the workflow kind used to isolate daily/weekly/monthly caches."""

    return (os.getenv("JEAC_REPORT_KIND") or "daily").strip().lower() or "daily"


def taipei_date(now: Optional[datetime] = None) -> date:
    """Resolve a run date in Asia/Taipei, with an explicit workflow override."""

    override = (os.getenv("JEAC_SAME_DAY_REUSE_DATE") or "").strip()
    if override:
        try:
            return date.fromisoformat(override)
        except ValueError:
            pass

    value = now
    if value is None:
        value = datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(TAIPEI_TZ).date()


def context_fingerprint(value: Any) -> str:
    """Return a stable short fingerprint for cache inputs that affect advice."""

    try:
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        serialized = repr(value)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


def cache_marker(
    *,
    now: Optional[datetime] = None,
    kind: Optional[str] = None,
    portfolio_context: Any = None,
) -> Dict[str, Any]:
    """Build the metadata stored with every reusable analysis snapshot."""

    marker = {
        "schema_version": SAME_DAY_REUSE_SCHEMA_VERSION,
        "report_kind": (kind or report_kind()).strip().lower(),
        "run_date": taipei_date(now).isoformat(),
    }
    if portfolio_context is not None:
        marker["portfolio_fingerprint"] = context_fingerprint(portfolio_context)
    return marker


def marker_matches(snapshot: Any, *, now: Optional[datetime] = None, kind: Optional[str] = None) -> bool:
    """Check whether a persisted context snapshot belongs to this run kind/date."""

    if not isinstance(snapshot, Mapping):
        return False
    marker = snapshot.get("same_day_reuse")
    if not isinstance(marker, Mapping):
        return False
    expected = cache_marker(now=now, kind=kind)
    return (
        marker.get("schema_version") == expected["schema_version"]
        and str(marker.get("report_kind") or "").strip().lower() == expected["report_kind"]
        and str(marker.get("run_date") or "").strip() == expected["run_date"]
    )


def required_regions() -> list[str]:
    """Return configured market regions for market-review cache validation."""

    raw = os.getenv("MARKET_REVIEW_REGION") or ""
    return [part.strip().lower() for part in raw.split(",") if part.strip()]


def meaningful_text(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return bool(text) and text not in {"n/a", "na", "none", "null", "unknown", "tbd", "未取得", "未取得／暫停判定", "資料缺失", "数据缺失"}


def analysis_payload_is_complete(payload: Any, snapshot: Any) -> bool:
    """Return whether a stock result is safe to reuse without re-analysis."""

    if not isinstance(payload, Mapping) or not isinstance(snapshot, Mapping):
        return False
    if payload.get("success") is not True or payload.get("data_status") != "available":
        return False
    if payload.get("sentiment_score") is None:
        return False
    if not all(
        meaningful_text(payload.get(field))
        for field in ("trend_prediction", "operation_advice", "analysis_summary")
    ):
        return False
    if not isinstance(payload.get("dashboard"), Mapping) or not payload.get("dashboard"):
        return False
    evidence = payload.get("technical_evidence")
    if not isinstance(evidence, Mapping) or evidence.get("data_status") not in {"available", "limited_history"}:
        return False
    # A rule-only result is intentionally retried.  It is a valid fail-safe
    # report, but it signals that the structured LLM output was not obtained.
    if str(evidence.get("llm_status") or "").strip() in {"schema_validation_failed", "provider_unavailable"}:
        return False
    if payload.get("data_missing_reasons"):
        return False
    # News retrieval is optional only when the service explicitly completed
    # with zero results.  A missing count means the fetch was skipped/failed.
    if "news_result_count" not in snapshot and not meaningful_text(snapshot.get("news_content")):
        return False
    return True


def market_payload_is_complete(payload: Any, regions: list[str]) -> bool:
    """Validate a persisted combined market-review payload before reuse."""

    if not isinstance(payload, Mapping) or not meaningful_text(payload.get("markdown_report")):
        return False
    markets = payload.get("markets")
    if regions and len(regions) > 1:
        if not isinstance(markets, Mapping):
            return False
        for region in regions:
            candidate = markets.get(region)
            if not isinstance(candidate, Mapping) or not meaningful_text(candidate.get("markdown_report")):
                return False
            integrity = candidate.get("data_integrity")
            if not isinstance(integrity, Mapping) or integrity.get("status") != "available":
                return False
        return True
    candidate = payload
    integrity = candidate.get("data_integrity")
    return isinstance(integrity, Mapping) and integrity.get("status") == "available"
