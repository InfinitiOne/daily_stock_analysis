from datetime import datetime, timezone

from data_provider.request_budget import DailyRequestBudget


def test_daily_budget_rejects_requests_after_limit(tmp_path):
    budget = DailyRequestBudget(tmp_path / "usage.json", daily_limit=2)
    now = datetime(2026, 7, 20, 12, tzinfo=timezone.utc)

    assert budget.try_reserve(now=now).allowed
    assert budget.try_reserve(now=now).allowed
    exhausted = budget.try_reserve(now=now)

    assert not exhausted.allowed
    assert exhausted.used == 2
    assert exhausted.remaining == 0


def test_daily_budget_resets_on_new_bucket(tmp_path):
    budget = DailyRequestBudget(tmp_path / "usage.json", daily_limit=1)
    first = datetime(2026, 7, 20, 23, 59, tzinfo=timezone.utc)
    second = datetime(2026, 7, 21, 0, 1, tzinfo=timezone.utc)

    assert budget.try_reserve(now=first).allowed
    assert not budget.try_reserve(now=first).allowed
    assert budget.try_reserve(now=second).allowed


def test_corrupt_counter_fails_closed(tmp_path):
    path = tmp_path / "usage.json"
    path.write_text("not json", encoding="utf-8")
    budget = DailyRequestBudget(path, daily_limit=25)

    result = budget.try_reserve(now=datetime(2026, 7, 20, tzinfo=timezone.utc))

    assert not result.allowed
    assert result.used == 25


def test_environment_limit_cannot_raise_free_plan_cap(monkeypatch, tmp_path):
    monkeypatch.setenv("ALPHAVANTAGE_MAX_REQUESTS_PER_DAY", "50")
    monkeypatch.setenv("ALPHAVANTAGE_BUDGET_FILE", str(tmp_path / "usage.json"))

    budget = DailyRequestBudget.from_env()

    assert budget.daily_limit == 25

