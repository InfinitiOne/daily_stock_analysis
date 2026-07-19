---
name: jeac-portfolio-risk
description: Assess JEAC Minervini-style portfolio stop risk, concentration, exposure and pyramiding before changes.
---

# JEAC Portfolio Risk

Use this skill before adding, reducing, or holding a Taiwan/US equity position. It produces conditional analysis only and never executes orders.

## Required inputs

Collect portfolio value/cash, symbol, quantity, cost, current price/as-of time, sector/theme, Stage, intended pivot/entry, structural stop, and the user’s risk limit. Mark missing fields and avoid false-precision totals.

## Review in order

1. Calculate position weight, loss to structural stop, open portfolio risk, issuer/sector/theme/market/currency concentration, and correlated exposure.
2. Check whether Stage, VCP/Pivot state and market regime permit new risk. `Stage 3/4`, a failed breakout, or a weak market cannot be masked by a good historical rating.
3. Require a defined stop and at least 2:1 reward-to-risk for new entries. Default risk per idea is 0.5–1.5% of portfolio value unless the user supplies a stricter rule.
4. Apply Minervini discipline: start small (normally up to 1/4 planned size), add only after the position proves itself and risk remains within budget, never average down, and never move a stop farther away. Keep cash as a valid position when follow-through weakens.
5. Treat a close decisively below the structural stop/pivot failure as a risk event; distinguish a conditional alert from an executed sale instruction.

## Output

Give a compact table for verified inputs, Stage/SEPA state, weight, stop risk, concentration and blocked calculations. Prioritize `維持`, `降低風險`, `等待確認`, or `不新增`, each with a measurable trigger. Keep FX, liquidity, tax, event and correlation caveats visible when relevant. Do not infer missing prices, stops, correlations, or totals.
