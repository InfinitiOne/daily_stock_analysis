# -*- coding: utf-8 -*-

import pytest

from src.llm.errors import (
    call_litellm_with_rate_limit_recovery,
    get_litellm_retry_after_seconds,
    is_litellm_rate_limit_error,
)


def test_rate_limit_retry_after_is_detected() -> None:
    error = RuntimeError("Rate limit reached. Please try again in 19.715s.")

    assert is_litellm_rate_limit_error(error) is True
    assert get_litellm_retry_after_seconds(error) == pytest.approx(19.715)


def test_rate_limit_recovery_waits_then_retries() -> None:
    attempts = []
    waits = []

    def call(_: dict) -> str:
        attempts.append("call")
        if len(attempts) == 1:
            raise RuntimeError("429 Too Many Requests; try again in 2 seconds")
        return "ok"

    result = call_litellm_with_rate_limit_recovery(
        call,
        model="openai/test",
        call_kwargs={},
        max_rate_limit_retries=2,
        max_wait_seconds=10,
        sleep=waits.append,
    )

    assert result == "ok"
    assert len(attempts) == 2
    assert waits == [2.0]


def test_non_rate_limit_error_is_not_retried() -> None:
    attempts = []

    def call(_: dict) -> str:
        attempts.append("call")
        raise RuntimeError("invalid request")

    with pytest.raises(RuntimeError, match="invalid request"):
        call_litellm_with_rate_limit_recovery(
            call,
            model="openai/test",
            call_kwargs={},
            sleep=lambda _: None,
        )

    assert attempts == ["call"]
