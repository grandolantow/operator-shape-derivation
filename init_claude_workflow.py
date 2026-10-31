#!/usr/bin/env python3
"""Plan or install a task-local Claude workflow from two CANNBot plugins.

No vendor init script is executed. Dry-run is the default; --apply writes only
TASK/.claude and TASK/CLAUDE.md, without replacing unowned entries.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shlex
import shutil
import sys
from pathlib import Path


GEN = "ops-direct-invoke"
GEN_AGENTS = {"ascendc-kernel-architect", "ascendc-kernel-design-reviewer",
              "ascendc-kernel-developer", "ascendc-kernel-reviewer"}
EVO = "ops-perf-evolution"
MANIFEST = ".claude/workflow-bootstrap-manifest.json"
PACKAGE = Path(__file__).resolve().parent
DEFAULT_WORKFLOW_SKILL = PACKAGE / "skills/ascend-op-workflow"


class BootstrapError(ValueError):
    pass


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def hash_tree(path: Path) -> str:
    if path.is_file():
        return hash_file(path)
    if not path.is_dir():
        raise BootstrapError(f"Missing source: {path}")
    h = hashlib.sha256()
    for relative, record in tree_records(path):
        h.update(relative.encode())
        h.update(record)
    return h.hexdigest()


def tree_records(root: Path) -> list[tuple[str, bytes]]:
    records = []
    resolved_root = root.resolve(strict=True)
    for item in sorted(root.rglob("*")):
        relative = item.relative_to(root)
        if "__pycache__" in relative.parts or item.suffix == ".pyc":
            continue
        if item.is_symlink():
            target = item.resolve(strict=True)
            if not target.is_relative_to(resolved_root):
                raise BootstrapError(f"Source link escapes root: {item} -> {target}")
            link_text = os.readlink(item)
            record = b"L\0" + link_text.encode() + b"\0" + target.relative_to(resolved_root).as_posix().encode()
        elif item.is_file():
            record = b"F\0" + bytes.fromhex(hash_file(item))
        else:
            continue
        records.append((relative.as_posix(), record))
    return records


def frontmatter_skills(path: Path, required: bool = True) -> list[str]:
    if not path.is_file():
        raise BootstrapError(f"Missing frontmatter: {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        raise BootstrapError(f"Missing frontmatter delimiter: {path}")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise BootstrapError(f"Unclosed frontmatter: {path}") from exc
    header = lines[1:end]
    try:
        index = header.index("skills:")
    except ValueError:
        if "skills: []" in header:
            return []
        if not required:
            return []
        raise BootstrapError(f"Missing skills whitelist: {path}")
    names: list[str] = []
    for line in header[index + 1 :]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"\s+-\s+([a-zA-Z0-9_-]+)\s*", line)
        if not match:
            break
        names.append(match.group(1))
    if not names:
        raise BootstrapError(f"Empty or malformed skills whitelist: {path}")
    return names


def source_skill(plugin: Path, shared: Path, name: str, local_first: bool) -> Path:
    roots = (plugin / "skills", shared) if local_first else (shared, plugin / "skills")
    for root in (*roots, shared.parent / "infra"):
        path = root / name
        if (path / "SKILL.md").is_file():
            return path.resolve()
    raise BootstrapError(f"Missing required skill {name} in {plugin.name} local/shared roots")


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def add_entry(entries: dict, rel: str, kind: str, source: Path | None = None, data: bytes | None = None) -> None:
    if rel in entries:
        raise BootstrapError(f"Duplicate planned destination: {rel}")
    if kind in ("link", "existing_source"):
        assert source is not None
        identity = hash_tree(source)
    elif kind == "copytree":
        assert source is not None
        identity = hash_tree(source)
    else:
        assert data is not None
        identity = sha_bytes(data)
    entries[rel] = {"kind": kind, "source": str(source) if source else None, "sha256": identity, "data": data}


def choose_skills(gen: Path, evo: Path, shared: Path) -> tuple[dict[str, Path], dict[str, list[str]]]:
    selected: dict[str, Path] = {}
    origins: dict[str, list[str]] = {}
    for plugin, local_first, exclude_triton in ((gen, False, True), (evo, True, False)):
        agents = sorted((plugin / "agents").glob("*.md"))
        agent_pattern = "ascendc-kernel-*" if plugin == gen else "*-*"
        names = list(frontmatter_skills(plugin / "AGENTS.md"))
        for agent in agents:
            if fnmatch.fnmatch(agent.stem, agent_pattern):
                names.extend(frontmatter_skills(agent, required=False))
        for name in dict.fromkeys(names):
            if exclude_triton and "triton" in name.lower():
                continue
            source = source_skill(plugin, shared, name, local_first)
            if name in selected and selected[name] != source:
                if hash_tree(selected[name]) != hash_tree(source):
                    raise BootstrapError(f"Cross-plugin skill collision {name}: {selected[name]} versus {source}")
            else:
                selected[name] = source
            origins.setdefault(name, []).append(f"{plugin.name}:{source}")
    return selected, origins


def agents_for(gen: Path, evo: Path) -> dict[str, Path]:
    selected: dict[str, Path] = {}
    for plugin, pattern in ((gen, "ascendc-kernel-*"), (evo, "*-*")):
        for path in sorted((plugin / "agents").glob("*.md")):
            if not fnmatch.fnmatch(path.stem, pattern):
                continue
            if path.stem in selected and hash_file(selected[path.stem]) != hash_file(path):
                raise BootstrapError(f"Cross-plugin agent collision: {path.stem}")
            selected[path.stem] = path.resolve()
    expected = GEN_AGENTS | {"lingxi-evo", "lingxi-partial", "ops-evo", "ops-partial"}
    missing = expected - set(selected)
    if missing:
        raise BootstrapError(f"Missing required agents: {', '.join(sorted(missing))}")
    return selected


def merged_hooks(gen: Path, evo: Path, task: Path) -> bytes:
    output: dict[str, object] = {"hooks": {}}
    runtime_gen = task / ".claude/runtime/generation"
    evo_hooks = task / ".claude/hooks/evolution"
    for plugin, replacement in ((gen, runtime_gen.as_posix()), (evo, evo_hooks.as_posix())):
        source = json.loads((plugin / "hooks/hooks.json").read_text(encoding="utf-8"))
        for event, groups in source["hooks"].items():
            for group in groups:
                copied = json.loads(json.dumps(group))
                for hook in copied["hooks"]:
                    command = hook.get("command")
                    if not isinstance(command, str) or "${CLAUDE_PLUGIN_ROOT}" not in command:
                        raise BootstrapError(f"Unsupported hook command in {plugin.name}: {command}")
                    tokens = shlex.split(command)
                    if plugin == gen:
                        tokens = [token.replace("${CLAUDE_PLUGIN_ROOT}", replacement) for token in tokens]
                        prefix = f"env CLAUDE_PLUGIN_ROOT={shlex.quote(replacement)} PROJECT_ROOT={shlex.quote(str(task))} "
                        match = re.search(r"/hooks/([\w.-]+)", " ".join(tokens))
                        source_hook = gen / "hooks" / match.group(1) if match else None
                    else:
                        tokens = [token.replace("${CLAUDE_PLUGIN_ROOT}/.claude/hooks", replacement) for token in tokens]
                        prefix = f"env CLAUDE_PROJECT_DIR={shlex.quote(str(task))} "
                        match = re.search(r"/evolution/([\w.-]+)", " ".join(tokens))
                        source_hook = evo / "hooks" / match.group(1) if match else None
                    if not source_hook or not source_hook.is_file():
                        raise BootstrapError(f"Missing referenced hook target: {source_hook}")
                    if plugin == gen:
                        # The vendor SessionStart may clone/clean asc-devkit. Inject
                        # the contract without running source installation logic.
                        hook["command"] = shlex.join([
                            "python3", str(runtime_gen / "session_context.py")
                        ])
                    else:
                        hook["command"] = prefix + shlex.join(tokens)
                output["hooks"].setdefault(event, []).append(copied)
    return json_bytes(output)


def plan(repo: Path, task: Path, workflow_skill: Path) -> tuple[dict, dict]:
    repo = repo.resolve(strict=True)
    task = task.resolve(strict=True)
    workflow_skill = workflow_skill.resolve(strict=True)
    if not task.is_dir():
        raise BootstrapError(f"Task directory is not a directory: {task}")
    skill_dir = workflow_skill if workflow_skill.is_dir() else workflow_skill.parent
    if not (skill_dir / "SKILL.md").is_file():
        raise BootstrapError(f"Missing workflow SKILL.md: {skill_dir}")
    if any("\\" in item.relative_to(skill_dir).as_posix() for item in skill_dir.rglob("*")):
        raise BootstrapError("Workflow upload contains literal Windows separators; normalize the staged paths first")
    gen = repo / "plugins-official" / GEN
    evo = repo / "plugins-community" / EVO
    shared = repo / "ops"
    for required in (gen / "init.sh", evo / "init.sh", shared):
        if not required.exists():
            raise BootstrapError(f"Missing CANNBot dependency: {required}")
    skills, origins = choose_skills(gen, evo, shared)
    # These are workflow dependencies even though the vendor AGENTS frontmatter
    # does not list them. Resolve them explicitly and fail on missing sources.
    for name, source, origin in (
        ("op-case-generator", shared / "op-case-generator", "repo-ops"),
        ("operator-shape-derivation", PACKAGE / "skills/operator-shape-derivation", "workflow-package"),
    ):
        if not (source / "SKILL.md").is_file():
            raise BootstrapError(f"Missing required workflow skill: {source / 'SKILL.md'}")
        source = source.resolve()
        if name in skills and hash_tree(skills[name]) != hash_tree(source):
            raise BootstrapError(f"Workflow skill collision {name}: {skills[name]} versus {source}")
        skills[name] = source
        origins.setdefault(name, []).append(f"{origin}:{source}")
    if "ascend-op-workflow" in skills and hash_tree(skills["ascend-op-workflow"]) != hash_tree(skill_dir):
        raise BootstrapError("Workflow skill name collides with vendor dependency")
    skills["ascend-op-workflow"] = skill_dir
    origins.setdefault("ascend-op-workflow", []).append(f"workflow:{skill_dir}")
    agents = agents_for(gen, evo)
    entries: dict = {}
    for name, source in sorted(skills.items()):
        rel = f".claude/skills/{name}"
        kind = "existing_source" if source == task / rel else "link"
        add_entry(entries, rel, kind, source)
    for name, source in sorted(agents.items()):
        add_entry(entries, f".claude/agents/{name}.md", "link", source)
    generation_context = (
        "Generation uses the AscendC direct-invoke pipeline. Source is read-only. "
        f"Read `{gen / 'AGENTS.md'}` and the four ascendc-kernel agent declarations. "
        f"Resolve workflows/ against `{gen / 'workflows'}`, including task-prompts.md, "
        "scripts and templates. Run scripts with the task as working directory. "
        f"Available devkit source: `{gen / 'asc-devkit'}` (check existence; do not install automatically).\n\n"
        + (gen / "AGENTS.md").read_text(encoding="utf-8")
    )
    context_payload = {"hookSpecificOutput": {
        "hookEventName": "SessionStart", "additionalContext": generation_context
    }}
    context_script = "import json\nprint(json.dumps(" + repr(context_payload) + ", ensure_ascii=False))\n"
    add_entry(entries, ".claude/runtime/generation/session_context.py", "file",
              data=context_script.encode("utf-8"))
    # Keep source hooks available for inspection; SessionStart uses the read-only shim.
    add_entry(entries, ".claude/runtime/generation/hooks", "copytree", gen / "hooks")
    add_entry(entries, ".claude/hooks/evolution", "copytree", evo / "hooks")
    add_entry(entries, ".claude/settings.json", "file", data=merged_hooks(gen, evo, task))
    add_entry(entries, ".claude/workflows", "link", gen / "workflows")
    devkit = gen / "asc-devkit"
    if devkit.is_dir():
        add_entry(entries, ".claude/asc-devkit", "link", devkit)
    # Keep direct runtime resources discoverable without modifying the source.
    add_entry(entries, ".claude/runtime/generation/AGENTS.md", "link", gen / "AGENTS.md")
    add_entry(entries, ".claude/runtime/generation/workflows", "link", gen / "workflows")
    if devkit.is_dir():
        add_entry(entries, ".claude/runtime/generation/asc-devkit", "link", devkit)
    claude = (
        "# Ascend operator workflow\n\n"
        "Use the task-local `.claude/skills/ascend-op-workflow/SKILL.md` as the coordinating workflow. "
        "Standard stages 0-4 belong to Codex, including selection and generation; Claude may execute stages 5-7 when assigned. Read the generation plugin's AGENTS.md only when that stage is explicitly assigned and the evolution plugin's "
        "AGENTS.md when entering optimization. Generation uses the AscendC direct-invoke Step 1-7 "
        "pipeline with ascendc-kernel-architect, ascendc-kernel-design-reviewer, "
        "ascendc-kernel-developer and ascendc-kernel-reviewer. Read the source "
        "workflows/task-prompts.md templates before each role invocation. Resolve source scripts "
        "and templates by absolute path, run scripts with the task as working directory, and "
        "keep source scripts/templates unchanged. Preserve each plugin stage boundary. "
        "Default auto scope generates the first implementation directly, then runs lightweight acceptance: "
        "full correctness and the frozen 10 performance cases, at most 3 ultra-large. "
        "Record measured R/G evidence and run workflow.py decision: deliver G when the target is met; "
        "enter optimization only when it is unmet, unless explicitly assigned full scope. "
        "Missing or conflicting measurements require acceptance work. Do not preselect kernel count, "
        "C/V splitting or intermediate GM layout. Every optimization round needs causal analysis "
        "and evidence-backed next hypotheses before further dispatch. "
        "If the task assigns Codex as supervisor, read `references/execution-modes.md` within the "
        "workflow skill, acknowledge the current dispatch, and execute within its contract and "
        "remaining budget. Maintain execution facts separately from supervisor acceptance; "
        "continue authorized work without waiting for approval on every implementation step.\n\n"
        f"Generation source: `{gen / 'AGENTS.md'}`\n\n"
        f"Optimization source: `{evo / 'AGENTS.md'}`\n"
    ).encode("utf-8")
    add_entry(entries, "CLAUDE.md", "file", data=claude)
    manifest = {
        "schema": 1, "repo_root": str(repo), "cannbot_root": str(repo),
        "workflow_root": str(PACKAGE), "task_dir": str(task),
        "workflow_skill": str(skill_dir), "skill_origins": origins,
        "source_contracts": {
            f"{plugin.name}/{name}": hash_file(plugin / name)
            for plugin in (gen, evo)
            for name in ("init.sh", "AGENTS.md", "hooks/hooks.json")
        },
        "entries": {name: {key: value for key, value in item.items() if key != "data"}
                    for name, item in sorted(entries.items())},
    }
    add_entry(entries, MANIFEST, "file", data=json_bytes(manifest))
    return entries, manifest


def actual_hash(path: Path, kind: str) -> str:
    if kind == "existing_source":
        if path.is_symlink() or not path.is_dir():
            raise BootstrapError(f"Registered source changed: {path}")
        return hash_tree(path)
    if kind == "link":
        if not path.is_symlink():
            raise BootstrapError(f"Managed link changed: {path}")
        return hash_tree(path.resolve(strict=True))
    if kind == "copytree":
        if path.is_symlink() or not path.is_dir():
            raise BootstrapError(f"Managed copy changed type: {path}")
        return hash_tree(path)
    if path.is_symlink() or not path.is_file():
        raise BootstrapError(f"Managed file changed type: {path}")
    return hash_file(path)


def check_existing(task: Path, entries: dict, manifest: dict) -> bool:
    manifest_path = task / MANIFEST
    if manifest_path.is_symlink():
        raise BootstrapError(f"Linked manifest is not allowed: {manifest_path}")
    for rel in entries:
        path = task / rel
        for parent in path.parents:
            if parent == task:
                break
            if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
                raise BootstrapError(f"Unsafe destination parent: {parent}")
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing != manifest:
            raise BootstrapError("Existing bootstrap manifest differs; refusing to change managed history")
        for rel, item in entries.items():
            path = task / rel
            if not path.exists() or actual_hash(path, item["kind"]) != item["sha256"]:
                raise BootstrapError(f"Managed entry changed: {path}")
            if item["kind"] == "link" and path.resolve(strict=True) != Path(item["source"]).resolve(strict=True):
                raise BootstrapError(f"Managed link target changed: {path}")
        return True
    for rel in entries:
        path = task / rel
        if entries[rel]["kind"] == "existing_source":
            if path.is_symlink() or not path.is_dir() or actual_hash(path, "existing_source") != entries[rel]["sha256"]:
                raise BootstrapError(f"Registered source changed: {path}")
            continue
        if path.exists() or path.is_symlink():
            raise BootstrapError(f"Existing unowned entry would be overwritten: {path}")
    return False


def apply(task: Path, entries: dict) -> None:
    for rel, item in entries.items():
        if rel == MANIFEST:
            continue
        if item["kind"] == "existing_source":
            continue
        path = task / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if item["kind"] == "link":
            path.symlink_to(item["source"], target_is_directory=Path(item["source"]).is_dir())
        elif item["kind"] == "copytree":
            shutil.copytree(item["source"], path, symlinks=True)
        else:
            path.write_bytes(item["data"])
    manifest = task / MANIFEST
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_bytes(entries[MANIFEST]["data"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cannbot-root", "--repo-root", dest="repo_root", required=True,
                        help="External CANNBot checkout; --repo-root is a compatibility alias")
    parser.add_argument("--task-dir", required=True)
    parser.add_argument("--workflow-skill", default=str(DEFAULT_WORKFLOW_SKILL),
                        help="Workflow skill directory (default: this package's skills/ascend-op-workflow)")
    parser.add_argument("--apply", action="store_true", help="Write planned task-local entries")
    args = parser.parse_args(argv)
    try:
        task = Path(args.task_dir).resolve(strict=True)
        entries, manifest = plan(Path(args.repo_root), task, Path(args.workflow_skill))
        installed = check_existing(task, entries, manifest)
        if args.apply and not installed:
            apply(task, entries)
            installed = True
        report = {"status": "installed" if installed else "dry-run", "task_dir": str(task),
                  "skills": len([x for x in entries if x.startswith(".claude/skills/")]),
                  "agents": len([x for x in entries if x.startswith(".claude/agents/")]),
                  "entries": list(entries), "manifest": str(task / MANIFEST)}
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0
    except (BootstrapError, OSError, json.JSONDecodeError) as exc:
        print(f"bootstrap: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
