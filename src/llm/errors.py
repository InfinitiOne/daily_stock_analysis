# -*- coding: utf-8 -*-
"""LiteLLM error classification and one-shot parameter recovery."""

from __future__ import annotations

import re
import time
from typing import Any, Callable, Dict, List, Optional

from src.llm.generation_params import (
    GenerationParamRecovery,
    apply_litellm_param_recovery,
    remember_litellm_generation_param_recovery,
)

_UNSUPPORTED_PARAM_MARKERS = (
    "unsupported",
    "not supported",
    "unrecognized",
    "unknown parameter",
    "not allowed",
    "invalid parameter",
    "does not support",
)

_TEMPERATURE_VALUE_PATTERN = r"-?\d+(?:\.\d+)?"
_ALLOWED_TEMPERATURE_PATTERNS = (
    re.compile(
        rf"\bonly\s+(?:the\s+)?(?:default\s+)?(?:temperature\s+)?(?:value\s+)?[\(`'\"]*(?P<value>{_TEMPERATURE_VALUE_PATTERN})(?!\w)"
    ),
    re.compile(
        rf"\bdefault(?:\s+temperature)?(?:\s+value)?\s*(?:is|=|:)\s*[\(`'\"]*(?P<value>{_TEMPERATURE_VALUE_PATTERN})(?!\w)"
    ),
)


def _collect_error_text(value: Any, seen: Optional[set] = None) -> List[str]:
    if seen is None:
        seen = set()
    if value is None:
        return []
    value_id = id(value)
    if value_id in seen:
        return []
    seen.add(value_id)

    chunks = [str(value)]
    if isinstance(value, BaseException):
        chunks.extend(_collect_error_text(getattr(value, "args", None), seen))
    if isinstance(value, dict):
        for item in value.values():
            chunks.extend(_collect_error_text(item, seen))
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            chunks.extend(_collect_error_text(item, seen))
    else:
        for attr in ("message", "body", "response", "llm_provider", "param"):
            if hasattr(value, attr):
                chunks.extend(_collect_error_text(getattr(value, attr), seen))
    return chunks


def _normalized_error_text(error: BaseException) -> str:
    return " ".join(chunk for chunk in _collect_error_text(error) if chunk).lower()


def _parse_allowed_temperature(text: str) -> Optional[float]:
    for segment in re.split(r"(?<!\d)\.(?!\d)|[!?;\n]+", text):
        if "only" not in segment:
            continue
        for pattern in _ALLOWED_TEMPERATURE_PATTERNS:
            match = pattern.search(segment[segment.find("only") :])
            if match is None:
                continue
            value = float(match.group("value"))
            if 0 <= value <= 2:
                return value
    return None


def classify_litellm_generation_param_error(
    error: BaseException,
) -> Optional[GenerationParamRecovery]:
    """Classify explicit provider parameter errors into a safe one-shot recovery."""
    text = _normalized_error_text(error)
    if not text:
        return None

    if "temperature" in text:
        allowed_temperature = _parse_allowed_temperature(text)
        if allowed_temperature is not None:
            return GenerationParamRecovery(
                set_params={"temperature": allowed_temperature},
                reason="temperature_default_only",
            )
        if "only" in text and "default" in text:
            return GenerationParamRecovery(
                omit_params=("temperature",),
                reason="temperature_default_only",
            )
        if any(marker in text for marker in _UNSUPPORTED_PARAM_MARKERS):
            return GenerationParamRecovery(
                omit_params=("temperature",),
                reason="temperature_unsupported",
            )

    for param in ("top_p", "presence_penalty", "frequency_penalty", "seed"):
        if param in text and any(marker in text for marker in _UNSUPPORTED_PARAM_MARKERS):
            return GenerationParamRecovery(
                omit_params=(param,),
                reason=f"{param}_unsupported",
            )
    return None


def call_litellm_with_param_recovery(
    call: Callable[[Dict[str, Any]], Any],
    *,
    model: str,
    call_kwargs: Dict[str, Any],
    model_list: Optional[List[Dict[str, Any]]] = None,
    cache_recovery: bool = True,
    logger: Optional[Any] = None,
    log_label: str = "[LiteLLM]",
) -> Any:
    """Call LiteLLM once, then retry once for explicit generation-parameter errors."""
    effective_kwargs = dict(call_kwargs)
    try:
        return call(effective_kwargs)
    except Exception as exc:
        recovery = classify_litellm_generation_param_error(exc)
        if recovery is None:
            raise
        retry_kwargs = apply_litellm_param_recovery(effective_kwargs, recovery)
        if retry_kwargs == effective_kwargs:
            raise
        if logger is not None:
            logger.warning(
                "%s %s generation parameter rejected (%s), retrying once with request-scoped recovery",
                log_label,
                model,
                recovery.reason,
            )
        response = call(retry_kwargs)
        if cache_recovery:
            remember_litellm_generation_param_recovery(
                model,
                recovery,
                model_list=model_list,
                request_overrides=retry_kwargs,
            )
        return response


_RATE_LIMIT_MARKERS = (
    "rate limit",
    "ratelimit",
    "too many requests",
    "status code 429",
    "http 429",
    "no deployments available",
)
_RETRY_AFTER_PATTERNS = (
    re.compile(r"(?:retry|try) again in\s*(?P<seconds>\d+(?:\.\d+)?)\s*(?:s|sec|second)", re.IGNORECASE),
    re.compile(r"retry-after\s*[:=]\s*(?P<seconds>\d+(?:\.\d+)?)", re.IGNORECASE),
)


def is_litellm_rate_limit_error(error: BaseException) -> bool:
    """Return true only for provider throttling errors that are safe to retry."""
    text = _normalized_error_text(error)
    return bool(text) and any(marker in text for marker in _RATE_LIMIT_MARKERS)


def get_litellm_retry_after_seconds(
    error: BaseException,
    *,
    default_seconds: float = 10.0,
    max_wait_seconds: float = 90.0,
) -> float:
    """Extract a provider retry delay without trusting unbounded error text."""
    text = _normalized_error_text(error)
    for pattern in _RETRY_AFTER_PATTERNS:
        match = pattern.search(text)
        if match is None:
            continue
        try:
            value = float(match.group("seconds"))
        except (TypeError, ValueError):
            continue
        if value >= 0:
            return min(value, max_wait_seconds)
    return min(max(default_seconds, 0.0), max_wait_seconds)


def call_litellm_with_rate_limit_recovery(
    call: Callable[[Dict[str, Any]], Any],
    *,
    model: str,
    call_kwargs: Dict[str, Any],
    model_list: Optional[List[Dict[str, Any]]] = None,
    cache_recovery: bool = True,
    logger: Optional[Any] = None,
    max_rate_limit_retries: int = 2,
    max_wait_seconds: float = 90.0,
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    """Wait for provider throttling windows, then retry the same logical call.

    A 429 is not treated as a failed investment analysis.  We honor the
    provider's retry delay when present and leave the original exception intact
    after the bounded retry budget is exhausted.
    """
    attempts = 0
    while True:
        try:
            return call_litellm_with_param_recovery(
                call,
                model=model,
                call_kwargs=call_kwargs,
                model_list=model_list,
                cache_recovery=cache_recovery,
                logger=logger,
            )
        except Exception as exc:
            if not is_litellm_rate_limit_error(exc) or attempts >= max_rate_limit_retries:
                raise
            wait_seconds = get_litellm_retry_after_seconds(
                exc,
                max_wait_seconds=max_wait_seconds,
            )
            if wait_seconds <= 0:
                raise
            attempts += 1
            if logger is not None:
                logger.warning(
                    "[LiteLLM] %s rate-limited; waiting %.1fs before retry %d/%d",
                    model,
                    wait_seconds,
                    attempts,
                    max_rate_limit_retries,
                )
            sleep(wait_seconds)
