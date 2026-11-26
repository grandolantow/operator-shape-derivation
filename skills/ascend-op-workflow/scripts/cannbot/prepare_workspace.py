#!/usr/bin/env python3
"""Prepare task-local CANNBot resources from an explicit read-only checkout.

No installation, hooks, jobs or NPU execution. Existing mutable resource copies
are retained on resume; staged copies become usable only after publication.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil


DEFAULT_SKILLS = ("evolution-world-model", "evolution-strategies", "evolution-knowledge")
SKILL_ROOT = Path(__file__).resolve().parents[2]


def tree_hash(root):
    result = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if "__pycache__" in relative.parts or path.suffix == ".pyc":
            continue
        if path.is_symlink():
            raise ValueError(f"Resource symlinks require an explicitly prepared source: {path}")
        if path.is_file():
            result.update(relative.as_posix().encode("utf-8"))
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    result.update(chunk)
    return result.hexdigest()


def skill_source(checkout, name):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        raise ValueError(f"Invalid skill name: {name}")
    roots = (checkout / "plugins-community/ops-perf-evolution/skills",
             checkout / "plugins-community/tilelang2ascendc-ops-generator/skills",
             checkout / "ops", checkout / "infra")
    sources = [root / name for root in roots if (root / name / "SKILL.md").is_file()]
    if not sources:
        raise ValueError(f"Missing CANNBot resource: {name}")
    if len({tree_hash(path) for path in sources}) != 1:
        raise ValueError(f"Conflicting CANNBot resource sources: {name}")
    return sources[0].resolve()


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def local_path(workspace, relative):
    path = workspace / relative
    if not path.resolve().is_relative_to(workspace):
        raise ValueError(f"Output escapes workspace: {path}")
    return path


def prepare(workspace, cannbot_root, skills=()):
    workspace = Path(workspace).expanduser().resolve()
    checkout = Path(cannbot_root).expanduser().resolve(strict=True)
    if (workspace.is_relative_to(checkout) or checkout.is_relative_to(workspace)
            or workspace.is_relative_to(SKILL_ROOT)):
        raise ValueError("Use a dedicated workspace outside CANNBot and the installed skill")
    marker = local_path(workspace, ".cannbot/workspace.json")
    record = json.loads(marker.read_text(encoding="utf-8")) if marker.is_file() else None
    if record and record.get("cannbot_root") != str(checkout):
        raise ValueError("Workspace belongs to a different CANNBot checkout")
    resources = dict(record["resources"]) if record else {}
    requested = {}
    for name in dict.fromkeys((*DEFAULT_SKILLS, *skills)):
        requested[f".claude/skills/{name}"] = skill_source(checkout, name)
    for relative, source in requested.items():
        identity = {"source": str(source), "sha256": tree_hash(source), "ready": False}
        if relative in resources:
            previous = resources[relative]
            if any(previous[key] != identity[key] for key in ("source", "sha256")):
                raise ValueError(f"CANNBot resource source changed: {source}")
        else:
            target = local_path(workspace, relative)
            if target.exists() or target.is_symlink():
                raise FileExistsError(f"Unowned resource destination: {target}")
            resources[relative] = identity
    # Preflight every persisted source and destination before any writes.
    for relative, entry in resources.items():
        source = Path(entry["source"]).resolve(strict=True)
        if not source.is_relative_to(checkout) or tree_hash(source) != entry["sha256"]:
            raise ValueError(f"CANNBot resource source changed: {source}")
        target = local_path(workspace, relative)
        if target.is_symlink():
            raise ValueError(f"Resource destination must be a local copy: {target}")
        if entry["ready"] and not target.is_dir():
            raise ValueError(f"Prepared resource is missing: {target}")
    control = local_path(workspace, ".cannbot")
    for relative in (".cannbot/env.sh", ".cannbot/env.ps1", ".cannbot/workspace.tmp", ".cannbot/staging"):
        local_path(workspace, relative)
    if not record and control.exists() and any(control.iterdir()):
        raise FileExistsError("Existing .cannbot/ is unowned; use an independent workspace")
    control.mkdir(parents=True, exist_ok=True)
    record = {"schema_version": 1, "cannbot_root": str(checkout), "workspace": str(workspace),
              "status": "preparing", "resources": resources, "automatic_hooks": False,
              "runtime_validated": False}
    write_json(marker, record)
    for relative, entry in resources.items():
        if entry["ready"]:
            continue
        target = local_path(workspace, relative)
        if target.exists():
            # Publication may have completed just before an interruption.
            if tree_hash(target) != entry["sha256"]:
                raise ValueError(f"Interrupted resource differs from its source: {target}")
        else:
            staging = local_path(workspace, f".cannbot/staging/{target.name}")
            shutil.copytree(entry["source"], staging, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            if tree_hash(staging) != entry["sha256"]:
                raise ValueError(f"Incomplete staged copy: {staging}")
            target.parent.mkdir(parents=True, exist_ok=True)
            staging.rename(target)
        entry["ready"] = True
        write_json(marker, record)
    environment = {"PYTHONDONTWRITEBYTECODE": "1", "CANNBOT_SOURCE_ROOT": str(checkout),
                   "CANNBOT_ROOT": str(workspace), "CANNBOT_SKILLS_DIR": str(workspace / ".claude/skills"),
                   "CLAUDE_PLUGIN_ROOT": str(workspace), "PROJECT_ROOT": str(workspace), "WORKDIR": str(workspace)}
    ps_quote = lambda value: "'" + value.replace("'", "''") + "'"
    (control / "env.sh").write_text(
        "\n".join(f"export {key}={shlex.quote(value)}" for key, value in environment.items()) + "\n",
        encoding="utf-8", newline="\n")
    (control / "env.ps1").write_text(
        "\n".join(f"$env:{key} = {ps_quote(value)}" for key, value in environment.items()) + "\n",
        encoding="utf-8", newline="\n")
    record.update(status="prepared", environment=environment)
    write_json(marker, record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--cannbot-root", type=Path, required=True)
    parser.add_argument("--skill", action="append", default=[], help="Additional needed resource; repeatable")
    args = parser.parse_args()
    try:
        result = prepare(args.workspace, args.cannbot_root, args.skill)
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(2, f"workspace preparation rejected: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
