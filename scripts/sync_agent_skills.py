#!/usr/bin/env python3
"""One-way installer for the JEAC repository skills.

`.claude/skills/` is the only version-controlled source.  This script copies
only the `jeac-*` skills to an agent-specific directory; it never reads a
target directory as an input and never writes back to the source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / ".claude" / "skills"
MANIFEST_NAME = ".jeac-skill-sync.json"
REQUIRED_SKILLS = frozenset(
    {
        "jeac-data-quality",
        "jeac-news-intel",
        "jeac-sepa-swing",
        "jeac-portfolio-risk",
        "jeac-backtest-validation",
    }
)


class SkillSyncError(RuntimeError):
    """Raised when a one-way skill sync cannot be performed safely."""


@dataclass(frozen=True)
class SourceSkill:
    name: str
    path: Path
    digest: str


@dataclass(frozen=True)
class SyncPlan:
    destination: Path
    create: tuple[str, ...]
    update: tuple[str, ...]
    unchanged: tuple[str, ...]
    prune: tuple[str, ...]


def _home_dir() -> Path:
    return Path(os.environ.get("HOME", str(Path.home()))).expanduser()


def _skill_digest(skill_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(skill_dir).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _frontmatter_name(skill_file: Path) -> str | None:
    lines = skill_file.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip().strip('"\'')
    return None


def discover_source_skills(source_dir: Path | None = None) -> tuple[SourceSkill, ...]:
    source_dir = SOURCE_DIR if source_dir is None else source_dir
    if not source_dir.is_dir():
        raise SkillSyncError(f"skill source is missing: {source_dir}")

    skills: list[SourceSkill] = []
    for skill_dir in sorted(source_dir.glob("jeac-*")):
        skill_file = skill_dir / "SKILL.md"
        if not skill_dir.is_dir() or not skill_file.is_file():
            continue
        declared_name = _frontmatter_name(skill_file)
        if declared_name != skill_dir.name:
            raise SkillSyncError(
                f"{skill_file.relative_to(ROOT)} declares {declared_name!r}; expected {skill_dir.name!r}"
            )
        skills.append(SourceSkill(skill_dir.name, skill_dir, _skill_digest(skill_dir)))

    names = {skill.name for skill in skills}
    missing = REQUIRED_SKILLS - names
    if missing:
        raise SkillSyncError(f"canonical source is missing required JEAC skills: {', '.join(sorted(missing))}")
    return tuple(skills)


def _read_manifest(destination: Path) -> dict[str, object]:
    manifest = destination / MANIFEST_NAME
    if not manifest.is_file():
        return {}
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SkillSyncError(f"invalid sync manifest: {manifest}: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise SkillSyncError(f"invalid sync manifest format: {manifest}")
    return payload


def _managed_names(manifest: dict[str, object]) -> set[str]:
    names = manifest.get("skills", [])
    if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
        return set()
    return {name for name in names if name.startswith("jeac-")}


def _ensure_safe_destination(destination: Path) -> Path:
    destination = destination.expanduser().resolve()
    source = SOURCE_DIR.resolve()
    if destination == source or destination.is_relative_to(source) or source.is_relative_to(destination):
        raise SkillSyncError("destination must not contain, or be contained by, .claude/skills")
    return destination


def build_plan(destination: Path, skills: Iterable[SourceSkill], *, prune: bool = False) -> SyncPlan:
    destination = _ensure_safe_destination(destination)

    create: list[str] = []
    update: list[str] = []
    unchanged: list[str] = []
    skill_list = tuple(skills)
    current_names = {skill.name for skill in skill_list}
    for skill in skill_list:
        target = destination / skill.name
        if not target.exists():
            create.append(skill.name)
        elif not target.is_dir():
            raise SkillSyncError(f"target path is not a directory: {target}")
        elif _skill_digest(target) == skill.digest:
            unchanged.append(skill.name)
        else:
            update.append(skill.name)

    stale: tuple[str, ...] = ()
    if prune and destination.is_dir():
        stale = tuple(sorted(name for name in _managed_names(_read_manifest(destination)) - current_names if (destination / name).exists()))

    return SyncPlan(destination, tuple(create), tuple(update), tuple(unchanged), stale)


def _replace_directory(source: Path, target: Path) -> None:
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{target.name}.sync-", dir=parent))
    shutil.rmtree(temporary)
    shutil.copytree(source, temporary)

    backup: Path | None = None
    try:
        if target.exists():
            backup = parent / f".{target.name}.backup"
            if backup.exists():
                shutil.rmtree(backup)
            target.replace(backup)
        temporary.replace(target)
    except Exception:
        if backup is not None and backup.exists() and not target.exists():
            backup.replace(target)
        raise
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
        if backup is not None and backup.exists():
            shutil.rmtree(backup)


def _write_manifest(destination: Path, skills: Iterable[SourceSkill]) -> None:
    payload = {
        "schema_version": 1,
        "managed_by": "scripts/sync_agent_skills.py",
        "source": ".claude/skills",
        "skills": [skill.name for skill in skills],
        "digests": {skill.name: skill.digest for skill in skills},
    }
    manifest = destination / MANIFEST_NAME
    temporary = manifest.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(manifest)


def apply_plan(plan: SyncPlan, skills: Iterable[SourceSkill]) -> None:
    skill_list = tuple(skills)
    by_name = {skill.name: skill for skill in skill_list}
    for name in (*plan.create, *plan.update):
        _replace_directory(by_name[name].path, plan.destination / name)
    for name in plan.prune:
        shutil.rmtree(plan.destination / name)
    _write_manifest(plan.destination, skill_list)


def check_destination(destination: Path, skills: Iterable[SourceSkill]) -> tuple[str, ...]:
    destination = _ensure_safe_destination(destination)
    errors: list[str] = []
    for skill in skills:
        target = destination / skill.name
        if not target.is_dir():
            errors.append(f"missing: {target}")
        elif _skill_digest(target) != skill.digest:
            errors.append(f"out of sync: {target}")
    return tuple(errors)


def target_destinations(target: str, destination: Path | None) -> tuple[Path, ...]:
    home = _home_dir()
    defaults = {
        "claude": Path(os.environ.get("JEAC_CLAUDE_SKILLS_DIR", home / ".claude" / "skills")),
        "codex": Path(os.environ.get("JEAC_CODEX_SKILLS_DIR", home / ".agents" / "skills")),
    }
    if target == "directory":
        if destination is None:
            raise SkillSyncError("--destination is required when --target directory is used")
        return (destination,)
    if destination is not None:
        raise SkillSyncError("--destination can only be used with --target directory")
    if target == "all":
        return (defaults["claude"], defaults["codex"])
    return (defaults[target],)


def _describe_plan(plan: SyncPlan) -> str:
    parts = []
    for label, names in (("create", plan.create), ("update", plan.update), ("unchanged", plan.unchanged), ("prune", plan.prune)):
        if names:
            parts.append(f"{label}={','.join(names)}")
    return "; ".join(parts) if parts else "no JEAC skills found"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="One-way installer for version-controlled JEAC skills.")
    parser.add_argument("--target", choices=("claude", "codex", "directory", "all"), required=True)
    parser.add_argument("--destination", type=Path, help="Custom skills directory; required for --target directory.")
    parser.add_argument("--apply", action="store_true", help="Apply the copy. Without this flag the script only prints a plan.")
    parser.add_argument("--check", action="store_true", help="Exit non-zero if a target does not match the canonical source.")
    parser.add_argument("--prune", action="store_true", help="Remove only stale skill folders recorded by this script's manifest.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.apply and args.check:
        raise SkillSyncError("--apply and --check cannot be used together")
    if args.prune and not args.apply:
        raise SkillSyncError("--prune requires --apply")

    skills = discover_source_skills()
    destinations = target_destinations(args.target, args.destination)
    if args.check:
        errors = [error for destination in destinations for error in check_destination(destination.expanduser(), skills)]
        if errors:
            print("[jeac-skill-sync] OUT OF SYNC", file=sys.stderr)
            print("\n".join(errors), file=sys.stderr)
            return 1
        print("[jeac-skill-sync] OK")
        return 0

    for destination in destinations:
        plan = build_plan(destination, skills, prune=args.prune)
        print(f"[jeac-skill-sync] {plan.destination}: {_describe_plan(plan)}")
        if args.apply:
            apply_plan(plan, skills)
            print(f"[jeac-skill-sync] synced {len(skills)} JEAC skills")
    if not args.apply:
        print("[jeac-skill-sync] dry run only; re-run with --apply to copy files")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SkillSyncError as exc:
        print(f"[jeac-skill-sync] ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
