# -*- coding: utf-8 -*-
"""Leakage-safe, long-only SEPA pivot backtest.

This module is intentionally independent from the historical-analysis
evaluation engine.  It tests a deterministic entry rule on OHLCV bars; it
does not forecast returns or submit orders.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any, Dict, List, Mapping, Sequence


@dataclass(frozen=True)
class SepaBacktestConfig:
    lookback_bars: int = 252
    base_bars: int = 50
    contraction_bars: int = 60
    pivot_volume_multiple: float = 1.4
    max_pivot_extension_pct: float = 5.0
    stop_loss_pct: float = 8.0
    reward_risk_multiple: float = 2.0
    max_holding_bars: int = 63
    commission_bps: float = 10.0
    slippage_bps: float = 5.0


class SepaBacktest:
    """Evaluate a documented SEPA/Stage 2/VCP/pivot rule using daily bars."""

    REQUIRED_FIELDS = ("date", "open", "high", "low", "close", "volume")

    @classmethod
    def run(
        cls, bars: Sequence[Mapping[str, Any]], config: SepaBacktestConfig = SepaBacktestConfig()
    ) -> Dict[str, Any]:
        normalized, reason = cls._normalize(bars)
        if reason:
            return {"validation_status": "blocked", "reason": reason, "trades": [], "summary": {}}
        if len(normalized) < config.lookback_bars + 2:
            return {
                "validation_status": "blocked",
                "reason": f"SEPA 回測至少需要 {config.lookback_bars + 2} 根完整日線。",
                "trades": [],
                "summary": {},
            }

        trades: List[Dict[str, Any]] = []
        signal_index = config.lookback_bars - 1
        while signal_index < len(normalized) - 1:
            signal = cls._signal(normalized, signal_index, config)
            if not signal:
                signal_index += 1
                continue
            trade = cls._simulate_trade(normalized, signal_index, signal, config)
            trades.append(trade)
            # A single capital allocation cannot enter another position before exit.
            signal_index = int(trade["exit_index"]) + 1

        return {
            "validation_status": "completed",
            "rule_version": "minervini-sepa-v2",
            "assumptions": {
                "entry": "signal close confirmed; next session open entry",
                "same_bar_stop_target": "stop_loss_first",
                "commission_bps_per_side": config.commission_bps,
                "slippage_bps_per_side": config.slippage_bps,
            },
            "trades": trades,
            "summary": cls._summary(trades, len(normalized)),
        }

    @classmethod
    def _normalize(cls, bars: Sequence[Mapping[str, Any]]):
        normalized: List[Dict[str, Any]] = []
        previous_date = None
        for index, bar in enumerate(bars):
            if not isinstance(bar, Mapping) or any(bar.get(key) is None for key in cls.REQUIRED_FIELDS):
                return [], f"第 {index + 1} 根日線缺少必要 OHLCV 欄位。"
            try:
                item = {key: float(bar[key]) if key != "date" else str(bar[key]) for key in cls.REQUIRED_FIELDS}
            except (TypeError, ValueError):
                return [], f"第 {index + 1} 根日線含非數值 OHLCV 欄位。"
            if item["open"] <= 0 or item["high"] <= 0 or item["low"] <= 0 or item["close"] <= 0 or item["volume"] < 0:
                return [], f"第 {index + 1} 根日線含無效 OHLCV 數值。"
            if item["low"] > item["high"]:
                return [], f"第 {index + 1} 根日線 low 高於 high。"
            if previous_date is not None and item["date"] <= previous_date:
                return [], "日線日期必須嚴格遞增，且不可重複。"
            previous_date = item["date"]
            normalized.append(item)
        return normalized, None

    @staticmethod
    def _mean(values: Sequence[float]) -> float:
        return sum(values) / len(values)

    @classmethod
    def _signal(cls, bars: Sequence[Dict[str, Any]], index: int, cfg: SepaBacktestConfig):
        history = bars[index - cfg.lookback_bars + 1 : index + 1]
        close = bars[index]["close"]
        ma50 = cls._mean([bar["close"] for bar in history[-50:]])
        ma150 = cls._mean([bar["close"] for bar in history[-150:]])
        ma200 = cls._mean([bar["close"] for bar in history[-200:]])
        prior_ma200 = cls._mean([bar["close"] for bar in history[-220:-20]])
        high_52w = max(bar["high"] for bar in history)
        low_52w = min(bar["low"] for bar in history)
        trend_template = (
            close > ma50 and close > ma150 and close > ma200,
            ma50 > ma150 > ma200,
            ma200 > prior_ma200,
            close >= low_52w * 1.25,
            close >= high_52w * 0.75,
            close > ma50,
        )
        trend_template_pass_count = sum(trend_template)
        stage_2 = trend_template_pass_count == len(trend_template)

        # Deterministic four-contraction VCP screen.  The signal stores the
        # count so the validation report can segment results without using
        # hindsight visual pattern labels.
        vcp_window = history[-48:]
        contractions = []
        for start in range(0, 48, 12):
            segment = vcp_window[start : start + 12]
            high = max(bar["high"] for bar in segment)
            low = min(bar["low"] for bar in segment)
            contractions.append(
                {
                    "range_pct": (high - low) / max(high, 1e-9) * 100,
                    "average_volume": cls._mean([bar["volume"] for bar in segment]),
                    "low": low,
                }
            )
        contraction_count = sum(
            contractions[position]["range_pct"] < contractions[position - 1]["range_pct"]
            for position in range(1, len(contractions))
        )
        volume_dry_up = contractions[-1]["average_volume"] <= contractions[-2]["average_volume"] * 0.8
        vcp = contraction_count >= 2 and contractions[-1]["range_pct"] <= 15 and volume_dry_up

        base = history[-49:-10]
        pivot = max(bar["high"] for bar in base)
        volume_ratio = bars[index]["volume"] / max(cls._mean([bar["volume"] for bar in history[-51:-1]]), 1e-9)
        pivot_confirmed = pivot <= close <= pivot * (1 + cfg.max_pivot_extension_pct / 100) and volume_ratio >= cfg.pivot_volume_multiple
        if not (stage_2 and vcp and pivot_confirmed):
            return None
        return {
            "pivot": pivot,
            "volume_ratio": volume_ratio,
            "signal_date": bars[index]["date"],
            "trend_template_pass_count": trend_template_pass_count,
            "vcp_contraction_count": contraction_count,
            "vcp_final_low": contractions[-1]["low"],
        }

    @classmethod
    def _simulate_trade(cls, bars, signal_index, signal, cfg):
        entry_index = signal_index + 1
        raw_entry = bars[entry_index]["open"]
        cost = (cfg.commission_bps + cfg.slippage_bps) / 10000
        entry_price = raw_entry * (1 + cost)
        stop = raw_entry * (1 - cfg.stop_loss_pct / 100)
        target = raw_entry * (1 + cfg.stop_loss_pct / 100 * cfg.reward_risk_multiple)
        last_index = min(len(bars) - 1, entry_index + cfg.max_holding_bars - 1)
        exit_index, raw_exit, exit_reason = last_index, bars[last_index]["close"], "time_exit"
        for index in range(entry_index, last_index + 1):
            bar = bars[index]
            if bar["low"] <= stop:  # Conservative when both stop and target occur in one daily bar.
                exit_index, raw_exit, exit_reason = index, stop, "stop_loss"
                break
            if bar["high"] >= target:
                exit_index, raw_exit, exit_reason = index, target, "take_profit"
                break
        exit_price = raw_exit * (1 - cost)
        return_pct = (exit_price / entry_price - 1) * 100
        return {
            "signal_date": signal["signal_date"], "entry_date": bars[entry_index]["date"], "exit_date": bars[exit_index]["date"],
            "entry_index": entry_index, "exit_index": exit_index, "entry_price": round(entry_price, 6),
            "exit_price": round(exit_price, 6), "pivot": round(signal["pivot"], 6),
            "pivot_volume_ratio": round(signal["volume_ratio"], 3), "exit_reason": exit_reason,
            "trend_template_pass_count": int(signal["trend_template_pass_count"]),
            "vcp_contraction_count": int(signal["vcp_contraction_count"]),
            "vcp_final_low": round(float(signal["vcp_final_low"]), 6),
            "return_pct": round(return_pct, 4), "holding_bars": exit_index - entry_index + 1,
        }

    @staticmethod
    def _summary(trades: Sequence[Dict[str, Any]], total_bars: int) -> Dict[str, Any]:
        if not trades:
            return {"trade_count": 0, "win_rate_pct": None, "expectancy_pct": None, "profit_factor": None, "max_drawdown_pct": None, "exposure_pct": 0.0}
        returns = [float(trade["return_pct"]) for trade in trades]
        wins = [value for value in returns if value > 0]
        losses = [value for value in returns if value < 0]
        equity, peak, max_drawdown = 1.0, 1.0, 0.0
        for value in returns:
            equity *= 1 + value / 100
            peak = max(peak, equity)
            max_drawdown = min(max_drawdown, (equity / peak - 1) * 100)
        return {
            "trade_count": len(trades), "win_rate_pct": round(len(wins) / len(trades) * 100, 2),
            "average_return_pct": round(sum(returns) / len(returns), 4), "median_return_pct": round(median(returns), 4),
            "expectancy_pct": round(sum(returns) / len(returns), 4),
            "profit_factor": round(sum(wins) / abs(sum(losses)), 4) if losses else None,
            "max_drawdown_pct": round(max_drawdown, 4),
            "exposure_pct": round(sum(int(trade["holding_bars"]) for trade in trades) / total_bars * 100, 2),
        }
