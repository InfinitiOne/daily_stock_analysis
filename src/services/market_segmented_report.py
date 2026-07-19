"""Shared Taiwan-first report composition for JEAC private reports.

The market review runner returns a structured payload for each region.  This
module keeps that structure intact and interleaves it with the matching stock
analysis instead of sorting every holding globally by score.
"""
from __future__ import annotations

from typing import Any, Iterable, List, Tuple


_TAIWAN_SUFFIXES = (".TW", ".TWO")


def is_taiwan_result(result: Any) -> bool:
    """Return whether a result belongs to the Taiwan equity/ETF section."""
    code = str(getattr(result, "code", "") or "").upper().strip()
    return code.endswith(_TAIWAN_SUFFIXES)


def split_results_by_market(results: Iterable[Any]) -> Tuple[List[Any], List[Any]]:
    """Preserve caller ordering while separating Taiwan from US holdings."""
    taiwan, us = [], []
    for result in results or []:
        (taiwan if is_taiwan_result(result) else us).append(result)
    return taiwan, us


def market_markdown(review_result: Any, region: str, fallback: str = "") -> str:
    """Read one market's report from the structured review contract.

    A legacy string fallback remains available for single-market/manual runs;
    scheduled Taiwan+US runs request the structured payload and never need to
    guess headings from model-generated text.
    """
    payload = getattr(review_result, "market_review_payload", None)
    if not isinstance(payload, dict):
        return fallback.strip()
    markets = payload.get("markets")
    if isinstance(markets, dict):
        item = markets.get(region)
        if isinstance(item, dict):
            return str(item.get("markdown_report") or "").strip()
        return ""
    if str(payload.get("region") or "").lower() == region:
        return str(payload.get("markdown_report") or fallback or "").strip()
    return ""


def build_taiwan_us_report(
    *,
    title: str,
    notifier: Any,
    results: Iterable[Any],
    report_type: Any,
    review_result: Any = None,
    legacy_market_report: str = "",
    evidence_markdown: str = "",
) -> str:
    """Build the fixed presentation order used by daily/weekly/monthly reports.

    Order is deliberately invariant:
    Taiwan market -> Taiwan holdings -> US market -> US holdings -> evidence.
    Empty market/holding sections are omitted rather than padded with an
    unavailable-data sentence.
    """
    taiwan_results, us_results = split_results_by_market(results)
    tw_market = market_markdown(review_result, "tw", legacy_market_report)
    us_market = market_markdown(review_result, "us")
    parts = [title]

    def add(heading: str, body: str) -> None:
        body = str(body or "").strip()
        if body:
            parts.append(f"## {heading}\n\n{body}")

    add("台股大盤走勢分析", tw_market)
    if taiwan_results:
        add("個別台股", notifier.generate_aggregate_report(taiwan_results, report_type))
    add("美股大盤走勢分析", us_market)
    if us_results:
        add("個別美股", notifier.generate_aggregate_report(us_results, report_type))
    # Evidence already owns stable table headings.  Append it directly to
    # avoid nesting a second "資料來源" heading around the source contract.
    evidence = str(evidence_markdown or "").strip()
    if evidence:
        parts.append(evidence)
    return "\n\n---\n\n".join(parts)
