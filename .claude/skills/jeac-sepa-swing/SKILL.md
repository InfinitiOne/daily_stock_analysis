---
name: jeac-sepa-swing
description: Evaluate 3–6 month Taiwan and US swing setups with Mark Minervini-style SEPA, Stage, VCP and pivot rules.
---

# JEAC Minervini SEPA Swing

Use this skill for 3–6 month Taiwan and US equity analysis. It creates a conditional research plan only; never place, route, or automate orders.

## Required evidence

Run `jeac-data-quality` first. Require adjusted daily OHLCV, an as-of date, and 252 sessions for a full Trend Template. State the benchmark used for relative strength (RS). If RS, fundamentals, or sponsorship are absent, mark that specific check `未提供`—do not turn technical evidence into a fabricated failure.

## Evaluate in this order

1. **Market regime.** Record the market trend and follow-through state. When the regime is weak, retain the setup but reduce or defer risk; do not force a daily trade.
2. **Minervini Trend Template.** Report each of these six checks and the pass count: price above MA50/150/200; MA50 > MA150 > MA200; MA200 above its value 20 sessions ago; price at least 25% above the 52-week low; price within 25% of the 52-week high; price above MA50. `Stage 2` requires all six, not merely a bullish short MA stack.
3. **Stage.** Give one current state and evidence: `Stage 1 築底`, `Stage 2 上升`, `Stage 3 頂部／轉弱`, or `Stage 4 下降`. Do not label Stage 2 if MA200 is not rising. State whether the result is a deterministic screen or needs visual review.
4. **Leadership.** Report benchmark-relative RS percentile/return, earnings and sales trend, profitability, liquidity, institutional sponsorship, and catalyst separately. Missing inputs lower evidence coverage; they are not bearish facts.
5. **VCP.** Identify chronological contractions, each with start/end date, high, low, range %, and average volume. A VCP candidate needs at least three progressively smaller contractions, a tight final contraction, and volume dry-up versus the prior contraction. Give `VCP 次數`, final-contraction low, and `VCP 候選／未形成`; never call a single compressed range a VCP.
6. **Pivot and buy zone.** State the pivot price, pivot source/base period, buy zone `[pivot, pivot × 1.05]`, breakout volume ratio versus 50-day average, structural stop (normally final-contraction low), stop risk %, Pivot Quality `High/Mid/Low`, and Breakout Risk `Low/Mid/High`. A confirmed breakout requires close inside the buy zone and at least 1.4× 50-day volume. Above the buy zone is `價格已延伸`, never a new entry.
7. **SEPA rating and plan.** Give `A+ / A / A- / B+ / B / C`, explain the scored evidence, then state a conditional entry, invalidation, first objective, and reward-to-risk. Reject new entries below 2:1 R/R.

## Output contract

Return this compact schema before prose:

| Field | Required value |
| --- | --- |
| Data / as-of | source status, date and adjusted-data policy |
| Trend Template | six checks and pass count |
| Stage | 1–4, label, evidence |
| VCP | count, ranges, volumes, final low, status |
| Pivot | price, buy zone, volume ratio, quality, risk |
| Plan | conditional trigger, stop, target, R/R, action |

Use `符合條件`, `等待確認`, `可觀察`, or `不符合`; explain the failing rule. For securities with less than 252 bars, provide supported short-term MA/volume facts and say `長週期 SEPA 不適用（歷史不足）`; do not populate fake Stage/VCP/Pivot fields. Never average down or widen a stop. Default risk per idea is 0.5–1.5% of portfolio value unless a stricter JEAC policy is supplied.
