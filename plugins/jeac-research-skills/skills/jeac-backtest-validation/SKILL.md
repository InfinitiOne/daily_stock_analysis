---
name: jeac-backtest-validation
description: Validate JEAC Minervini SEPA, Stage, VCP, pivot and risk rules with leakage-safe out-of-sample evidence.
---

# JEAC Backtest Validation

Use this skill before claiming that a JEAC SEPA/Stage/VCP rule has historical support. A backtest is evidence, not a forecast or trading authorization.

## Version the rule before testing

Document universe, dates, adjusted-data policy, benchmark, Trend Template six checks, Stage rules, objective VCP-contraction algorithm, pivot/buy-zone trigger, entry timing, stop/target/time exits, add-on rules, position limits, cost/slippage, and delisting treatment. Assign a rule version and log every parameter change.

## Prevent bias

1. Use only information available at the signal timestamp; enter no earlier than next tradable session after a daily close signal.
2. Make VCP deterministic. A visual chart sample cannot be a backtest rule; persist contraction count, ranges, volume dry-up, pivot and final-contraction stop for each signal.
3. Keep delisted names when possible; disclose survivorship and benchmark limitations.
4. Split development/validation periods, run rolling walk-forward tests, and test Taiwan and US independently before combining results.
5. Reject missing or non-adjusted OHLCV rather than filling gaps.

## Required report

Report trade count, hit rate, average/median return, expectancy, profit factor, maximum drawdown, exposure, costs, date range, and signal-to-entry delay. Segment results by market regime, Stage, SEPA rating, VCP count, Pivot Quality and Breakout Risk. Include sensitivity around volume, stop, buy-zone and holding-period parameters. Flag small samples, concentration, unstable parameters, and any evidence of leakage. If prerequisites fail, report `驗證未完成` with the missing item—never infer success from charts.
