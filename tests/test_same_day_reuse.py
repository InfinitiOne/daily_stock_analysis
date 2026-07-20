from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.analyzer import AnalysisResult
from src.core.pipeline import StockAnalysisPipeline
from src.services.same_day_reuse import analysis_payload_is_complete, cache_marker


def _complete_payload() -> dict:
    return {
        "code": "2330.TW",
        "name": "台積電",
        "sentiment_score": 78,
        "trend_prediction": "偏多",
        "operation_advice": "觀察",
        "analysis_summary": "均線與量價條件完整。",
        "dashboard": {"core_conclusion": {"one_sentence": "條件完整"}},
        "success": True,
        "data_status": "available",
        "data_missing_reasons": [],
        "technical_evidence": {"data_status": "available", "history_bars": 420},
        "model_used": "groq/llama-3.3-70b-versatile",
    }


def test_same_day_analysis_accepts_only_complete_payload(monkeypatch) -> None:
    monkeypatch.setenv("JEAC_SAME_DAY_REUSE_ENABLED", "true")
    monkeypatch.setenv("JEAC_REPORT_KIND", "daily")
    monkeypatch.setenv("JEAC_SAME_DAY_REUSE_DATE", "2026-07-20")
    snapshot = {
        "same_day_reuse": cache_marker(kind="daily"),
        "news_result_count": 2,
        "news_search_completed": True,
    }

    assert analysis_payload_is_complete(_complete_payload(), snapshot)


def test_same_day_analysis_rejects_rule_only_llm_fallback(monkeypatch) -> None:
    monkeypatch.setenv("JEAC_SAME_DAY_REUSE_DATE", "2026-07-20")
    payload = _complete_payload()
    payload["technical_evidence"]["llm_status"] = "provider_unavailable"
    snapshot = {
        "same_day_reuse": cache_marker(kind="daily"),
        "news_result_count": 0,
        "news_search_completed": True,
    }

    assert not analysis_payload_is_complete(payload, snapshot)


def test_pipeline_restores_complete_same_day_result(monkeypatch) -> None:
    monkeypatch.setenv("JEAC_SAME_DAY_REUSE_ENABLED", "true")
    monkeypatch.setenv("JEAC_REPORT_KIND", "daily")
    monkeypatch.setenv("JEAC_SAME_DAY_REUSE_DATE", "2026-07-20")
    payload = _complete_payload()
    snapshot = {
        "same_day_reuse": cache_marker(kind="daily"),
        "news_result_count": 1,
        "news_search_completed": True,
        "enhanced_context": {"fundamental_context": {"status": "available"}},
    }
    row = SimpleNamespace(
        id=17,
        raw_result=json.dumps(payload, ensure_ascii=False),
        context_snapshot=json.dumps(snapshot, ensure_ascii=False),
    )
    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline.db = MagicMock()
    pipeline.db.get_latest_same_day_analysis_history.return_value = row

    result = pipeline._try_reuse_same_day_analysis(
        code="2330.TW",
        report_type=SimpleNamespace(value="simple"),
        query_id="new-query",
    )

    assert isinstance(result, AnalysisResult)
    assert result.query_id == "new-query"
    assert result.technical_evidence["same_day_reuse"] is True
    assert result.fundamental_context == {"status": "available"}
    pipeline.db.get_latest_same_day_analysis_history.assert_called_once()
