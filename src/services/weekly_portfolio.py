# -*- coding: utf-8 -*-
"""Secure runtime loader for the JEAC weekly portfolio master file.

The real portfolio file is intentionally runtime-only.  Do not commit it to a
public repository: GitHub Actions writes it from a repository secret before a
weekly run starts.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable, List, Optional


CURRENT_PORTFOLIO_FILENAME = "08-01_Current_Portfolio.md"
_TW_ETF_ALPHA_RE = re.compile(r"^\d{5}[A-Z]$", re.IGNORECASE)
_TW_NUMERIC_RE = re.compile(r"^\d{4,5}$")
_US_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$", re.IGNORECASE)


class PortfolioLoadError(RuntimeError):
    """Raised when the required weekly portfolio master cannot be read."""


@dataclass(frozen=True)
class PortfolioHolding:
    symbol: str
    source_code: str


@dataclass(frozen=True)
class WeeklyPortfolio:
    path: Path
    holdings: List[PortfolioHolding]

    @property
    def symbols(self) -> List[str]:
        return [holding.symbol for holding in self.holdings]

    def to_context(self) -> dict:
        return {
            "source_file": self.path.name,
            "holding_count": len(self.holdings),
            "symbols": self.symbols,
        }


def normalize_portfolio_symbol(value: str) -> Optional[str]:
    """Normalize supported portfolio symbols without guessing market data."""
    code = str(value or "").strip().upper()
    if not code:
        return None
    if code.endswith((".TW", ".TWO")):
        base, suffix = code.rsplit(".", 1)
        if _TW_NUMERIC_RE.fullmatch(base) or _TW_ETF_ALPHA_RE.fullmatch(base):
            return f"{base}.{suffix}"
        return None
    if _TW_NUMERIC_RE.fullmatch(code) or _TW_ETF_ALPHA_RE.fullmatch(code):
        # Weekly portfolio master uses Taiwan local codes; retain explicit Yahoo
        # suffixes throughout the data-provider route.
        return f"{code}.TW"
    if _US_TICKER_RE.fullmatch(code):
        return code
    return None


def _table_cells(line: str) -> Iterable[str]:
    return (cell.strip() for cell in line.strip().strip("|").split("|"))


def _extract_symbol(line: str) -> Optional[str]:
    if "|" not in line:
        return None
    cells = list(_table_cells(line))
    header_cells = {
        "code",
        "ticker",
        "symbol",
        "name",
        "名稱",
        "代號",
        "股票",
        "quantity",
        "average cost",
        "currency",
    }
    if not cells or any(cell.lower() in header_cells for cell in cells):
        return None
    if all(set(cell) <= {"-", ":", " "} for cell in cells):
        return None
    for cell in cells:
        # Accept a clean code cell only; never infer a code from free-form notes.
        symbol = normalize_portfolio_symbol(cell)
        if symbol:
            return symbol
    return None


def load_current_portfolio(
    portfolio_path: str | Path = CURRENT_PORTFOLIO_FILENAME,
) -> WeeklyPortfolio:
    """Read the fixed current-portfolio master and produce a de-duplicated list."""
    path = Path(portfolio_path)
    if not path.is_file():
        raise PortfolioLoadError(
            f"Required weekly portfolio master is missing: {CURRENT_PORTFOLIO_FILENAME}"
        )

    symbols: List[PortfolioHolding] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        symbol = _extract_symbol(line)
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(PortfolioHolding(symbol=symbol, source_code=symbol))

    if not symbols:
        raise PortfolioLoadError(
            f"{CURRENT_PORTFOLIO_FILENAME} did not contain any supported holding codes"
        )
    return WeeklyPortfolio(path=path, holdings=symbols)


def merge_weekly_symbols(
    portfolio: WeeklyPortfolio,
    candidate_codes: Iterable[str] = (),
) -> List[str]:
    """Return holdings first, then valid candidates; candidates never replace holdings."""
    symbols = list(portfolio.symbols)
    seen = set(symbols)
    for raw in candidate_codes:
        symbol = normalize_portfolio_symbol(raw)
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    return symbols
