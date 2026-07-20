# -*- coding: utf-8 -*-
"""Tests for the one-way JEAC skill installer."""

import json
from pathlib import Path

import pytest

from scripts import sync_agent_skills


def _write_skill(source: Path, name: str, body: str = "instructions") -> Path:
    skill_dir = source / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f'---\nname: "{name}"\ndescription: "test"\n---\n\n# {name}\n\n{body}\n', encoding="utf-8"
    )
    return skill_dir


def _all_required_skills(source: Path) -> None:
    for name in sync_agent_skills.REQUIRED_SKILLS:
        _write_skill(source, name)


def test_discover_source_skills_requires_the_five_jeac_skills(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write_skill(source, "jeac-data-quality")

    with pytest.raises(sync_agent_skills.SkillSyncError, match="missing required JEAC skills"):
        sync_agent_skills.discover_source_skills(source)


def test_apply_plan_copies_only_jeac_skills_and_check_detects_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _all_required_skills(source)
    _write_skill(source, "jeac-extra", "extra")
    _write_skill(source, "not-jeac", "must not be installed")
    monkeypatch.setattr(sync_agent_skills, "SOURCE_DIR", source)
    skills = sync_agent_skills.discover_source_skills()
    destination = tmp_path / "codex" / "skills"

    plan = sync_agent_skills.build_plan(destination, skills)
    assert set(plan.create) == {skill.name for skill in skills}
    sync_agent_skills.apply_plan(plan, skills)

    assert (destination / "jeac-data-quality" / "SKILL.md").is_file()
    assert not (destination / "not-jeac").exists()
    assert sync_agent_skills.check_destination(destination, skills) == ()

    (destination / "jeac-sepa-swing" / "SKILL.md").write_text("changed", encoding="utf-8")
    assert "out of sync:" in sync_agent_skills.check_destination(destination, skills)[0]


def test_prune_removes_only_manifest_managed_skills(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _all_required_skills(source)
    monkeypatch.setattr(sync_agent_skills, "SOURCE_DIR", source)
    skills = sync_agent_skills.discover_source_skills()
    destination = tmp_path / "target"
    sync_agent_skills.apply_plan(sync_agent_skills.build_plan(destination, skills), skills)

    stale = destination / "jeac-retired"
    stale.mkdir()
    (stale / "SKILL.md").write_text("retired", encoding="utf-8")
    unrelated = destination / "unrelated-skill"
    unrelated.mkdir()
    (unrelated / "SKILL.md").write_text("keep", encoding="utf-8")
    manifest = json.loads((destination / sync_agent_skills.MANIFEST_NAME).read_text(encoding="utf-8"))
    manifest["skills"].append("jeac-retired")
    (destination / sync_agent_skills.MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")

    plan = sync_agent_skills.build_plan(destination, skills, prune=True)
    assert plan.prune == ("jeac-retired",)
    sync_agent_skills.apply_plan(plan, skills)
    assert not stale.exists()
    assert unrelated.exists()


def test_target_directory_requires_an_explicit_destination(tmp_path: Path) -> None:
    with pytest.raises(sync_agent_skills.SkillSyncError, match="--destination is required"):
        sync_agent_skills.target_destinations("directory", None)
    assert sync_agent_skills.target_destinations("directory", tmp_path) == (tmp_path,)


def test_all_target_uses_claude_and_codex_default_locations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    assert sync_agent_skills.target_destinations("all", None) == (
        tmp_path / ".claude" / "skills",
        tmp_path / ".agents" / "skills",
    )


def test_destination_cannot_be_the_canonical_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / ".claude" / "skills"
    source.mkdir(parents=True)
    _all_required_skills(source)
    monkeypatch.setattr(sync_agent_skills, "SOURCE_DIR", source)
    skills = sync_agent_skills.discover_source_skills()

    with pytest.raises(sync_agent_skills.SkillSyncError, match="destination must not"):
        sync_agent_skills.build_plan(source, skills)
    with pytest.raises(sync_agent_skills.SkillSyncError, match="destination must not"):
        sync_agent_skills.check_destination(source, skills)
