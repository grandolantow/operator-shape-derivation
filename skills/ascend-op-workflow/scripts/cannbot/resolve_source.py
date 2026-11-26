#!/usr/bin/env python3
"""Resolve the CANNBot source for a generation or optimization task."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory


UPSTREAM = "https://gitcode.com/cann/cannbot.git"
BRANCH = "master"
VENDOR = "vendor/cannbot-skills"
DIRECT = "plugins-official/ops-direct-invoke"
EVOLUTION = "plugins-community/ascendc-ops-perf-evolution"


def git(root, *args):
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    if result.returncode:
        raise ValueError(result.stderr.strip() or f"git {args[0]} failed")
    return result.stdout.strip()


def describe(root, managed=False):
    generation = root / DIRECT / "skills/ops-direct-invoke/SKILL.md"
    if generation.is_file():
        skills = root / VENDOR
        optimization = root / EVOLUTION / "AGENTS.md"
        world_model = skills / "community/ops/ascendc-evolution-world-model/SKILL.md"
        if not (skills / ".git").exists() or not world_model.is_file():
            raise ValueError(f"Initialize the CANNBot skills submodule at {skills}")
        skills_commit = git(skills, "rev-parse", "HEAD")
        app_commit = git(root, "rev-parse", "HEAD")
        if managed and skills_commit != git(root, "rev-parse", f"HEAD:{VENDOR}"):
            raise ValueError("CANNBot skills checkout differs from the application gitlink")
        layout = "application"
    else:
        if managed:
            raise ValueError(f"Expected the CANNBot application at {root}")
        generation = root / DIRECT / "AGENTS.md"
        optimization = root / "plugins-community/ops-perf-evolution/AGENTS.md"
        skills = root
        app_commit = None
        skills_commit = git(root, "rev-parse", "HEAD") if (root / ".git").exists() else None
        layout = "legacy"
    for entry in (generation, optimization):
        if not entry.is_file():
            raise ValueError(f"Missing CANNBot entry point: {entry}")
    return {
        "layout": layout,
        "source_root": str(root),
        "skills_root": str(skills),
        "application_commit": app_commit,
        "skills_commit": skills_commit,
        "generation_entry": str(generation),
        "optimization_entry": str(optimization),
        "default_branch": BRANCH if managed else None,
    }


def resolve(task_dir, cannbot_root=None):
    task_dir = Path(task_dir).resolve(strict=True)
    deps = task_dir / ".workflow-deps"
    if not deps.resolve().is_relative_to(task_dir):
        raise ValueError(f"Dependency directory escapes the task: {deps}")
    manifest = deps / "cannbot-source.json"
    managed_root = deps / "cannbot"
    explicit = Path(cannbot_root).expanduser().resolve(strict=True) if cannbot_root else None

    if manifest.is_file():
        recorded = json.loads(manifest.read_text(encoding="utf-8"))
        root = Path(recorded["source_root"])
        if explicit and explicit != root:
            raise ValueError(f"This task already uses CANNBot at {root}")
        if describe(root, managed=recorded["default_branch"] is not None) != recorded:
            raise ValueError(f"CANNBot source changed since the task was pinned: {manifest}")
        return recorded

    installed = task_dir / ".agents/ascend-op-workflow-install.json"
    if explicit is None and installed.is_file():
        configured = json.loads(installed.read_text(encoding="utf-8")).get("cannbot_root")
        if configured:
            explicit = Path(configured).resolve(strict=True)

    deps.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="cannbot-", dir=deps) as temp:
        staging = Path(temp)
        if explicit:
            record = describe(explicit)
        else:
            if not managed_root.exists():
                candidate = staging / "source"
                git(staging, "clone", "--depth", "1", "--single-branch", "--branch", BRANCH,
                    UPSTREAM, str(candidate))
                git(candidate, "submodule", "update", "--init", "--", VENDOR)
                describe(candidate, managed=True)
                try:
                    candidate.rename(managed_root)
                except OSError:
                    if not managed_root.is_dir():
                        raise
            record = describe(managed_root, managed=True)

        # Publish a complete record and use the already-published version if another
        # process resolved this task while the checkout was being prepared.
        pending = staging / manifest.name
        pending.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
        try:
            manifest.hardlink_to(pending)
        except FileExistsError:
            return resolve(task_dir, explicit)

    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-dir", type=Path, required=True)
    parser.add_argument("--cannbot-root", type=Path, help="Explicit CANNBot checkout override")
    args = parser.parse_args()
    try:
        result = resolve(args.task_dir, args.cannbot_root)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"CANNBot source resolution failed: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
