---
name: jeac-backtest-validation
description: Validate JEAC trading rules with leakage-safe backtests and out-of-sample evidence.
---

# JEAC Backtest Validation

Specify universe, data adjustment, signal, next-session entry, exits, costs, slippage, and position limits before measuring results. Use only information known at the decision time; never enter on the same daily close that defines the signal. Include incomplete-data and survivorship limitations.

Report trade count, hit rate, average/median return, expectancy, profit factor, drawdown, exposure, assumptions, market-regime breakdown, and out-of-sample/walk-forward evidence. If the rule or data cannot support a valid test, report `驗證未完成`; do not imply predictive power.
