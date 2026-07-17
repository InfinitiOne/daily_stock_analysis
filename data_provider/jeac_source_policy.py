"""JEAC Enterprise 5.0 data-source policy and evidence quality helpers.

The policy is intentionally independent from provider implementations.  It
gives callers one stable contract for source priority, official-source status,
cross-validation and disclosure of missing evidence.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping, Optional


@dataclass(frozen=True)
class SourcePolicy:
    market: str
    dataset: str
    preferred: tuple[str, ...]
    official: tuple[str, ...]
    minimum_sources: int = 2


@dataclass(frozen=True)
class EvidenceQuality:
    status: str
    source_count: int
    official_source_present: bool
    cross_validated: bool
    sources: tuple[str, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_POLICIES: dict[tuple[str, str], SourcePolicy] = {
    ("tw", "quote"): SourcePolicy(
        "tw", "quote", ("TWSE", "TPEx", "YfinanceFetcher", "FinMind"), ("TWSE", "TPEx")
    ),
    ("tw", "institution"): SourcePolicy(
        "tw", "institution", ("TWSE-T86", "TPEx-OpenAPI"), ("TWSE-T86", "TPEx-OpenAPI"), 1
    ),
    ("tw", "fundamental"): SourcePolicy(
        "tw", "fundamental", ("MOPS", "company_ir", "YfinanceFundamentalAdapter"), ("MOPS",)
    ),
    ("us", "quote"): SourcePolicy(
        "us", "quote", ("exchange", "FinnhubFetcher", "AlphaVantageFetcher", "YfinanceFetcher"), ("exchange",)
    ),
    ("us", "fundamental"): SourcePolicy(
        "us", "fundamental", ("company_ir", "SEC", "YfinanceFundamentalAdapter"), ("company_ir", "SEC")
    ),
}


def get_source_policy(market: str, dataset: str) -> Optional[SourcePolicy]:
    """Return the normalized JEAC source policy for a market/dataset pair."""
    return _POLICIES.get(((market or "").strip().lower(), (dataset or "").strip().lower()))


def assess_evidence(
    market: str,
    dataset: str,
    sources: Iterable[str],
    *,
    missing_fields: Iterable[str] = (),
    values_consistent: Optional[bool] = None,
) -> EvidenceQuality:
    """Classify evidence without inventing unavailable verification.

    ``values_consistent`` must only be supplied after a caller has actually
    compared equivalent dates, units and sessions.  Multiple source labels by
    themselves never count as successful cross-validation.
    """
    normalized = tuple(dict.fromkeys(str(item).strip() for item in sources if str(item).strip()))
    missing = tuple(str(item).strip() for item in missing_fields if str(item).strip())
    policy = get_source_policy(market, dataset)
    official = bool(policy and any(source in policy.official for source in normalized))
    required = policy.minimum_sources if policy else 2
    cross_validated = len(normalized) >= required and values_consistent is True

    limitations: list[str] = []
    if policy and not official:
        limitations.append("official_source_missing")
    if len(normalized) < required:
        limitations.append("insufficient_independent_sources")
    elif values_consistent is None:
        limitations.append("values_not_compared")
    elif values_consistent is False:
        limitations.append("source_values_conflict")
    limitations.extend(f"missing_field:{field}" for field in missing)

    if not normalized:
        status = "unavailable"
    elif cross_validated and not missing:
        status = "verified"
    else:
        status = "partial"
    return EvidenceQuality(
        status=status,
        source_count=len(normalized),
        official_source_present=official,
        cross_validated=cross_validated,
        sources=normalized,
        limitations=tuple(limitations),
    )


def assess_source_chain(
    market: str,
    dataset: str,
    source_chain: Iterable[Mapping[str, Any]],
    *,
    missing_fields: Iterable[str] = (),
) -> dict[str, Any]:
    """Assess an existing DSA source chain using successful providers only."""
    sources = [
        str(item.get("provider") or "").strip()
        for item in source_chain
        if isinstance(item, Mapping) and item.get("result") == "ok"
    ]
    return assess_evidence(
        market,
        dataset,
        sources,
        missing_fields=missing_fields,
        values_consistent=None,
    ).to_dict()
