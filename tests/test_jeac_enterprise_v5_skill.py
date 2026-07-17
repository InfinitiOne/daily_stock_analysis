from pathlib import Path

from src.agent.skills.base import load_skill_from_yaml


def test_jeac_enterprise_v5_is_default_framework_skill():
    path = Path(__file__).resolve().parents[1] / "strategies" / "jeac_enterprise_v5.yaml"
    skill = load_skill_from_yaml(path)

    assert skill.name == "jeac_enterprise_v5"
    assert skill.category == "framework"
    assert skill.default_active is True
    assert skill.default_router is True
    assert skill.default_priority < 10
    assert "JEAC Score" in skill.instructions
    assert "jeac_data_quality" in skill.instructions
    assert "不得虛構" in skill.instructions


def test_jeac_framework_requires_existing_data_tools_only():
    path = Path(__file__).resolve().parents[1] / "strategies" / "jeac_enterprise_v5.yaml"
    skill = load_skill_from_yaml(path)

    assert set(skill.required_tools) == {
        "get_daily_history",
        "analyze_trend",
        "get_realtime_quote",
        "search_stock_news",
        "get_stock_info",
    }
