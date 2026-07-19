# -*- coding: utf-8 -*-

import pandas as pd

from src.analyzer import AnalysisResult, apply_placeholder_fill, build_data_unavailable_result, check_content_integrity
from src.core.pipeline import StockAnalysisPipeline
from src.stock_analyzer import BuySignal, StockTrendAnalyzer, TrendAnalysisResult


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
    assert evidence["sepa"] == "未取得／暫停判定"
    assert evidence["short_term_analysis_available"] is True
    assert evidence["short_term_lookback_bars"] == 20
    assert evidence["ma5"] == 10.0
    assert "可進行短期趨勢" in evidence["reason"]


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
