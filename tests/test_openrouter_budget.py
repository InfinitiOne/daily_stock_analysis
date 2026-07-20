from __future__ import annotations

from src.llm.openrouter_budget import OpenRouterRequestBudget, is_openrouter_route


def test_budget_is_capped_by_one_key_daily_limit() -> None:
    budget = OpenRouterRequestBudget(run_budget=99, per_key_daily_limit=50)
    assert sum(budget.reserve() for _ in range(51)) == 50
    assert budget.used == 50
    assert budget.remaining == 0


def test_workflow_budget_can_be_smaller_than_provider_limit() -> None:
    budget = OpenRouterRequestBudget(run_budget=12, per_key_daily_limit=50)
    assert sum(budget.reserve() for _ in range(13)) == 12


def test_openrouter_route_detected_from_base_url() -> None:
    model_list = [
        {
            "model_name": "openai/qwen/qwen3-32b",
            "litellm_params": {
                "model": "openai/qwen/qwen3-32b",
                "api_base": "https://openrouter.ai/api/v1",
            },
        }
    ]
    assert is_openrouter_route("openai/qwen/qwen3-32b", model_list=model_list)
