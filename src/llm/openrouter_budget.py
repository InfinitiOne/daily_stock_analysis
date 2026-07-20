"""Process-local request budget for OpenRouter fallback calls.

LiteLLM's Router chooses a deployment internally.  The guard therefore caps
the aggregate number of OpenRouter attempts in a process; this is safe for
every configured key because no single key can receive more attempts than the
aggregate cap.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_OPENROUTER_DAILY_LIMIT_PER_KEY = 50
DEFAULT_OPENROUTER_RUN_BUDGET = 12


def _read_int(name: str, default: int, *, minimum: int = 0, maximum: int = 10000) -> int:
    try:
        value = int(os.getenv(name, str(default)).strip())
    except (AttributeError, TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


class OpenRouterRequestBudget:
    """Thread-safe process-local cap for OpenRouter requests."""

    def __init__(self, *, run_budget: int, per_key_daily_limit: int) -> None:
        self.per_key_daily_limit = max(0, int(per_key_daily_limit))
        # Aggregate cap <= one key's daily limit is independent of Router's
        # internal key-selection strategy.
        self.run_budget = max(0, min(int(run_budget), self.per_key_daily_limit))
        self._used = 0
        self._lock = threading.Lock()

    @classmethod
    def from_environment(cls) -> "OpenRouterRequestBudget":
        per_key_limit = _read_int(
            "LLM_OPENROUTER_MAX_REQUESTS_PER_KEY",
            DEFAULT_OPENROUTER_DAILY_LIMIT_PER_KEY,
        )
        run_budget = _read_int(
            "LLM_OPENROUTER_MAX_REQUESTS_PER_RUN",
            DEFAULT_OPENROUTER_RUN_BUDGET,
        )
        budget = cls(run_budget=run_budget, per_key_daily_limit=per_key_limit)
        logger.info(
            "OpenRouter request budget enabled: %d attempt(s)/run; per-key daily limit=%d",
            budget.run_budget,
            budget.per_key_daily_limit,
        )
        return budget

    def reserve(self) -> bool:
        """Reserve one provider attempt; return False when the cap is spent."""
        with self._lock:
            if self._used >= self.run_budget:
                return False
            self._used += 1
            return True

    @property
    def used(self) -> int:
        with self._lock:
            return self._used

    @property
    def remaining(self) -> int:
        with self._lock:
            return max(0, self.run_budget - self._used)


_PROCESS_BUDGET: Optional[OpenRouterRequestBudget] = None
_PROCESS_BUDGET_LOCK = threading.Lock()


def get_openrouter_request_budget() -> OpenRouterRequestBudget:
    """Return one shared budget so multiple analyzer instances share the cap."""
    global _PROCESS_BUDGET
    with _PROCESS_BUDGET_LOCK:
        if _PROCESS_BUDGET is None:
            _PROCESS_BUDGET = OpenRouterRequestBudget.from_environment()
        return _PROCESS_BUDGET


def is_openrouter_route(model: Any, provider: Any = "", model_list: Any = None) -> bool:
    """Identify an OpenRouter route from provider/model/base URL metadata."""
    text = " ".join(str(value or "").lower() for value in (model, provider))
    if "openrouter" in text:
        return True
    for entry in model_list or []:
        if not isinstance(entry, dict):
            continue
        params = entry.get("litellm_params") or {}
        if not isinstance(params, dict):
            continue
        entry_models = (entry.get("model_name"), params.get("model"))
        if str(model) not in {str(item) for item in entry_models if item is not None}:
            continue
        base_url = str(params.get("api_base") or params.get("base_url") or "").lower()
        if "openrouter.ai" in base_url:
            return True
    return False


def reset_openrouter_request_budget_for_tests() -> None:
    """Reset the process singleton for isolated tests."""
    global _PROCESS_BUDGET
    with _PROCESS_BUDGET_LOCK:
        _PROCESS_BUDGET = None
