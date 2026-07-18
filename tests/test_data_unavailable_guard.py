# -*- coding: utf-8 -*-

from src.analyzer import apply_placeholder_fill, build_data_unavailable_result, check_content_integrity
from src.stock_analyzer import BuySignal, StockTrendAnalyzer


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
