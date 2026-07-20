"""Regression checks for daily-analysis runtime guardrails."""

from pathlib import Path

from src.analyzer import GeminiAnalyzer


ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/00-daily-analysis.yml"


def test_llm_request_timeout_is_bounded(monkeypatch) -> None:
    monkeypatch.delenv("LLM_REQUEST_TIMEOUT_SECONDS", raising=False)
    assert GeminiAnalyzer._get_llm_request_timeout_seconds() == 45.0

    monkeypatch.setenv("LLM_REQUEST_TIMEOUT_SECONDS", "9999")
    assert GeminiAnalyzer._get_llm_request_timeout_seconds() == 180.0

    monkeypatch.setenv("LLM_REQUEST_TIMEOUT_SECONDS", "invalid")
    assert GeminiAnalyzer._get_llm_request_timeout_seconds() == 45.0


def test_daily_workflow_has_queue_and_provider_time_guards() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    # Report jobs share the Alpha Vantage counter, so they must queue instead
    # of cancelling the active run and losing its persisted budget state.
    assert "group: jeac-provider-budget" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "timeout-minutes: 25" in workflow
    for key in (
        "LLM_REQUEST_TIMEOUT_SECONDS",
        "LLM_RATE_LIMIT_MAX_RETRIES",
        "LLM_RATE_LIMIT_MAX_WAIT_SECONDS",
        "FUNDAMENTAL_STAGE_TIMEOUT_SECONDS",
    ):
        assert key in workflow
