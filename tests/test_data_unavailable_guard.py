# -*- coding: utf-8 -*-

import pandas as pd

from src.analyzer import (
    AnalysisResult,
    apply_placeholder_fill,
    build_data_unavailable_result,
    check_content_integrity,
    fill_price_position_if_needed,
)
from src.core.pipeline import StockAnalysisPipeline
from src.stock_analyzer import BuySignal, StockTrendAnalyzer, TrendAnalysisResult, TrendStatus, VolumeStatus


def test_core_data_unavailable_is_not_scored_or_marked_for_sale() -> None:
    result = build_data_unavailable_result("00403A.TW", "ETF", reasons=["daily bars unavailable"])

    assert result.data_status == "unavailable"
    assert result.sentiment_score is None
    assert result.decision_type == "hold"
    assert result.action == "watch"
    assert result.operation_advice == "未取得／暫停判定"

    passed, missing = check_content_integrity(result)
    apply_placeholder_fill(result, ["sentiment_score"])
    assert passed is True
    assert missing == []
    assert result.sentiment_score is None

    paused = build_data_unavailable_result(
        "NVDA", "NVIDIA", reasons=["LLM 429"], data_status="paused"
    )
    assert paused.data_status == "paused"
    assert paused.sentiment_score is None
    assert paused.action == "watch"


def test_empty_history_never_becomes_a_zero_score_sell_signal() -> None:
    trend = StockTrendAnalyzer().analyze(None, "00403A.TW")

    assert trend.is_evaluable is False
    assert trend.signal_score is None
    assert trend.buy_signal == BuySignal.WAIT


def test_new_listing_history_is_limited_not_unavailable() -> None:
    frame = pd.DataFrame(
        {
            "open": [10.0] * 47,
            "high": [10.2] * 47,
            "low": [9.8] * 47,
            "close": [10.0] * 47,
            "volume": [1000] * 47,
        }
    )

    evidence = StockTrendAnalyzer._build_weekly_technical_evidence(frame)

    assert evidence["data_status"] == "limited_history"
    # A newly listed instrument has usable short-term data, but insufficient
    # history for Minervini's long-cycle SEPA judgement.  This is distinct
    # from a data-fetch failure and must remain visible to the report layer.
    assert evidence["sepa"] == "不適用（歷史不足）"
    assert evidence["short_term_analysis_available"] is True
    assert evidence["short_term_lookback_bars"] == 20
    assert evidence["ma5"] == 10.0
    assert evidence["short_term_support"] == 9.8
    assert evidence["short_term_resistance"] == 10.2
    assert evidence["volume_ratio_5d"] == 1.0
    assert "可進行短期趨勢" in evidence["reason"]
    assert "短歷史標的" in evidence["setup_summary"]
    assert "不適用" in evidence["setup_summary"]


def test_llm_schema_failure_preserves_rule_based_core_data_for_weekly_integrity() -> None:
    failed = AnalysisResult(
        code="2330.TW",
        name="台積電",
        sentiment_score=65,
        trend_prediction="看多",
        operation_advice="買入",
        success=False,
        error_message="LLM response is not valid JSON; analysis result will not be persisted",
    )
    trend = TrendAnalysisResult(
        code="2330.TW",
        signal_score=42,
        technical_evidence={"data_status": "available", "history_bars": 557},
    )
    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)

    result = pipeline._preserve_rule_based_result_after_llm_schema_failure(
        failed,
        trend_result=trend,
        report_language="zh-TW",
    )

    assert result.success is True
    assert result.data_status == "available"
    assert result.sentiment_score == 42
    assert result.operation_advice == "觀察"
    assert result.decision_type == "hold"
    assert result.technical_evidence["llm_status"] == "schema_validation_failed"


def test_schema_validation_failed_marker_also_preserves_rule_based_result() -> None:
    failed = AnalysisResult(
        code="00403A.TW",
        name="主動統一升級50",
        sentiment_score=13,
        trend_prediction="強勢空頭",
        operation_advice="賣出",
        success=False,
        error_message="GenerationError: schema_validation_failed",
    )
    trend = TrendAnalysisResult(
        code="00403A.TW",
        signal_score=13,
        current_price=10.12,
        ma5=10.05,
        ma10=10.0,
        ma20=9.95,
        bias_ma5=0.7,
        trend_status=TrendStatus.STRONG_BEAR,
        volume_status=VolumeStatus.NORMAL,
        volume_ratio_5d=1.12,
        volume_trend="量能正常",
        technical_evidence={
            "data_status": "limited_history",
            "short_term_support": 9.8,
            "short_term_resistance": 10.4,
        },
    )
    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)

    result = pipeline._preserve_rule_based_result_after_llm_schema_failure(
        failed,
        trend_result=trend,
        report_language="zh-TW",
    )
    fill_price_position_if_needed(result, trend)

    assert result.success is True
    assert result.operation_advice == "觀察"
    assert result.action == "watch"
    sniper = result.dashboard["battle_plan"]["sniper_points"]
    assert sniper["ideal_buy"] == 10.4
    assert sniper["secondary_buy"] == 9.8
    assert sniper["stop_loss"] == 9.8
    perspective = result.dashboard["data_perspective"]
    assert perspective["price_position"]["support_level"] == 9.8
    assert perspective["price_position"]["resistance_level"] == 10.4
    assert perspective["volume_analysis"]["volume_ratio"] == 1.12
    assert "規則化技術結論" in result.analysis_summary
    assert "突破 10.40" in result.buy_reason
    assert "LLM" not in result.dashboard["phase_decision"]["confidence_reason"]
