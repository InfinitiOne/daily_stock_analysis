# -*- coding: utf-8 -*-

from src.services.weekly_portfolio import (
    load_current_portfolio,
    merge_weekly_symbols,
    normalize_portfolio_symbol,
)


def test_normalize_portfolio_symbol_routes_taiwan_etfs() -> None:
    assert normalize_portfolio_symbol("00403A") == "00403A.TW"
    assert normalize_portfolio_symbol("00940") == "00940.TW"
    assert normalize_portfolio_symbol("2330") == "2330.TW"
    assert normalize_portfolio_symbol("NVDA") == "NVDA"


def test_portfolio_master_holds_cannot_be_overridden_by_candidates(tmp_path) -> None:
    master = tmp_path / "08-01_Current_Portfolio.md"
    master.write_text(
        "| Code | Name |\n"
        "| --- | --- |\n"
        "| NVDA | NVIDIA |\n"
        "| 00403A | ETF |\n"
        "| 00940 | ETF |\n",
        encoding="utf-8",
    )

    portfolio = load_current_portfolio(master)
    assert portfolio.symbols == ["NVDA", "00403A.TW", "00940.TW"]
    assert merge_weekly_symbols(portfolio, ["00403A.TW", "2330"]) == [
        "NVDA",
        "00403A.TW",
        "00940.TW",
        "2330.TW",
    ]
