---
name: jeac-data-quality
description: Validate Taiwan and US market, fundamental and benchmark data before JEAC analysis or reports.
---

# JEAC Data Quality

Use this skill before SEPA scoring, VCP/Stage analysis, portfolio action, or a market report.

## Source and coverage contract

1. State market, symbol, exchange, currency, timezone, as-of timestamp, adjustment policy, and source route. Taiwan equities use TWSE/TPEx/MOPS/issuer sources first; US equities use issuer IR/SEC/exchange sources first. ETFs use their dedicated supported route and must not be treated as common stock.
2. For full Minervini evaluation require 252 adjusted daily OHLCV sessions; for a pivot require at least 50 sessions and volume; for RS require the benchmark series and common calendar; for fundamentals require dated filing or issuer evidence.
3. Check monotonically ordered dates, duplicate bars, invalid OHLCV values, stale quotes, calendar/units, corporate actions, and source conflicts. Never replace a timeout, empty response, or malformed value with zero.
4. Record each provider attempt as `ok`, `empty`, `timeout`, `stale`, or `invalid`, including the reason. Do not use old data to fill a newer report unless it is explicitly labelled historical.

## Decision gates

| Status | Meaning | Permitted output |
| --- | --- | --- |
| `verified` | Required inputs are timely and consistent | Complete rule-based analysis. |
| `partial` | Only non-critical evidence is missing | Give supported calculations and name blocked fields. |
| `blocked` | A required input is stale, absent, or contradictory | Do not score or recommend; name the exact prerequisite. |

For a new listing or short-history ETF, the correct result is `partial`: report short-term facts, then `長週期 SEPA 不適用（歷史不足）`. It is not a bearish signal.

## Report contract

Attach source/as-of/coverage to every conclusion. Omit unneeded empty sections. Use `未取得` only for a specific unavailable field; use `不適用（歷史不足）` for a rule whose lookback cannot exist. Never invent support/resistance, news sentiment, turnover, institutional flows, RS, target prices, or missing OHLCV.
