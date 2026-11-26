#!/usr/bin/env python3
"""Install the Ascend operator workflow into one Codex task.

[Role] Install task-local workflow and CANNBot skills.
[Invariants] Existing source checkouts are read-only; dry-run is the default.
[Side-Effect Policy] --apply may clone the default CANNBot source into the task.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory
from pathlib import Path


GEN = "ops-direct-invoke"
GEN_AGENTS = {"ascendc-kernel-architect", "ascendc-kernel-design-reviewer",
              "ascendc-kernel-developer", "ascendc-kernel-reviewer"}
EVO = "ops-perf-evolution"
MANIFEST = ".agents/ascend-op-workflow-install.json"
PACKAGE = Path(__file__).resolve().parent
CANNBOT_URL = "https://gitcode.com/cann/cannbot.git"
CANNBOT_BRANCH = "master"
CANNBOT_CHECKOUT = ".workflow-deps/cannbot"
CANNBOT_VENDOR = "vendor/cannbot-skills"


class InstallError(ValueError):
    pass


def is_reparse(path: Path) -> bool:
    """Detect Windows junctions as well as symlinks on Python before 3.12."""
    if path.is_symlink():
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except FileNotFoundError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def reject_reparse_chain(path: Path) -> None:
    path = path.absolute()
    for item in (path, *path.parents):
        if is_reparse(item):
            raise InstallError(f"Reparse point in destination path: {item}")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def filesystem_path(path: Path) -> Path:
    if os.name != "nt":
        return path
    raw = str(path.absolute())
    if raw.startswith("\\\\?\\"):
        return path
    if raw.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + raw[2:])
    return Path("\\\\?\\" + raw)


def tree_digest(path: Path) -> str:
    path = filesystem_path(path)
    if not path.is_dir():
        raise InstallError(f"Missing skill directory: {path}")
    h = hashlib.sha256()
    for item in sorted(path.rglob("*")):
        relative = item.relative_to(path)
        if "__pycache__" in relative.parts or item.suffix == ".pyc":
            continue
        if item.is_symlink():
            raise InstallError(f"Source symlink cannot be copied without a symlink: {item}")
        if item.is_file():
            h.update(relative.as_posix().encode("utf-8"))
            h.update(bytes.fromhex(digest(item)))
    return h.hexdigest()


def frontmatter_skills(path: Path, required: bool = True) -> list[str]:
    if not path.is_file():
        raise InstallError(f"Missing dependency declaration: {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        raise InstallError(f"Missing frontmatter: {path}")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise InstallError(f"Unclosed frontmatter: {path}") from exc
    header = lines[1:end]
    if "skills: []" in header:
        return []
    try:
        start = header.index("skills:")
    except ValueError:
        if required:
            raise InstallError(f"Missing skills whitelist: {path}")
        return []
    names = []
    for line in header[start + 1 :]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"\s+-\s+([A-Za-z0-9_-]+)\s*", line)
        if not match:
            break
        names.append(match.group(1))
    if not names and required:
        raise InstallError(f"Empty skills whitelist: {path}")
    return names


def required_agents(plugin: Path, pattern: str) -> list[Path]:
    return [item for item in sorted((plugin / "agents").glob("*.md"))
            if fnmatch.fnmatch(item.stem, pattern)]


def source_skill(plugin: Path, shared: Path, name: str, local_first: bool) -> Path:
    roots = (plugin / "skills", shared) if local_first else (shared, plugin / "skills")
    for root in (*roots, shared.parent / "infra"):
        candidate = root / name
        if (candidate / "SKILL.md").is_file():
            return candidate.resolve()
    raise InstallError(f"Missing required skill {name} for {plugin.name}")


def packaged_skills(result: dict, origins: dict, workflow: Path) -> None:
    if not (workflow / "SKILL.md").is_file():
        raise InstallError(f"Missing source: {workflow / 'SKILL.md'}")
    result["ascend-op-workflow"] = workflow
    origins.setdefault("ascend-op-workflow", []).append(f"workflow:{workflow}")
    bundled = PACKAGE / "skills"
    required_shape = bundled / "operator-shape-derivation"
    if not (required_shape / "SKILL.md").is_file():
        raise InstallError(f"Missing required packaged skill: {required_shape}")
    for source in sorted(bundled.iterdir()):
        if not source.is_dir() or not (source / "SKILL.md").is_file() or source.name == "ascend-op-workflow":
            continue
        source = source.resolve()
        if source.name in result and tree_digest(result[source.name]) != tree_digest(source):
            raise InstallError(f"Packaged skill collision {source.name}: {result[source.name]} versus {source}")
        result[source.name] = source
        origins.setdefault(source.name, []).append(f"packaged:{source}")


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "core.longpaths=true", "-C", str(root), *args],
        capture_output=True, encoding="utf-8",
        errors="replace", env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    if result.returncode:
        raise InstallError(f"git {args[0]} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def clone_cannbot(root: Path) -> None:
    root.parent.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="cannbot-", dir=root.parent) as temp:
        staging = Path(temp) / "checkout"
        git(root.parent, "clone", "--depth", "1", "--branch", CANNBOT_BRANCH,
            "--single-branch", CANNBOT_URL, str(staging))
        git(staging, "submodule", "update", "--init", "--", CANNBOT_VENDOR)
        staging.rename(root)


def application_skills(repo: Path, workflow: Path) -> tuple[dict[str, Path], dict]:
    shared = repo / CANNBOT_VENDOR
    if not (repo / ".git").exists() or not (shared / ".git").exists():
        raise InstallError(f"CANNBot application and skills must be initialized Git checkouts: {repo}")
    plugins = [repo / "plugins-official" / GEN]
    evolution = repo / "plugins-community/ascendc-ops-perf-evolution"
    if (evolution / "plugin-sources.json").is_file():
        plugins.append(evolution)

    result, origins, contracts = {}, {}, {}
    for plugin in plugins:
        declaration = plugin / "plugin-sources.json"
        config = json.loads(declaration.read_text(encoding="utf-8"))
        source_root = (repo / config["skillsRepository"]).resolve()
        if not source_root.is_relative_to(repo):
            raise InstallError(f"CANNBot skill source escapes the checkout: {source_root}")
        for relative in config["skills"]:
            source = (source_root / relative).resolve()
            if source.name == "workflow-orchestrator" or source.name.startswith("gitcode-"):
                continue
            if not source.is_relative_to(repo) or not (source / "SKILL.md").is_file():
                raise InstallError(f"Missing or invalid CANNBot skill: {source}")
            if source.name in result and result[source.name] != source:
                if tree_digest(result[source.name]) != tree_digest(source):
                    raise InstallError(f"Cross-plugin skill collision: {source.name}")
            result.setdefault(source.name, source)
            origins.setdefault(source.name, []).append(f"{plugin.name}:{source}")
        contracts[str(declaration.relative_to(repo))] = digest(declaration)

    case_generator = shared / "ops/op-case-generator"
    if (case_generator / "SKILL.md").is_file() and case_generator.name not in result:
        result[case_generator.name] = case_generator
        origins[case_generator.name] = [f"workflow:{case_generator}"]
    packaged_skills(result, origins, workflow)
    return result, {
        "skill_origins": origins,
        "vendor_contracts": contracts,
        "vendor_agents": {},
        "cannbot_revisions": {
            "application": git(repo, "rev-parse", "HEAD"),
            "skills": git(shared, "rev-parse", "HEAD"),
        },
    }


def discover(repo: Path | None, workflow: Path) -> tuple[dict[str, Path], dict]:
    if repo is None:
        skills, origins = {}, {}
        packaged_skills(skills, origins, workflow)
        return skills, {"skill_origins": origins, "vendor_contracts": {}, "vendor_agents": {}}
    gen = repo / "plugins-official" / GEN
    if (gen / "plugin-sources.json").is_file() and (repo / ".gitmodules").is_file():
        return application_skills(repo, workflow)
    evo = repo / "plugins-community" / EVO
    shared = repo / "ops"
    for source in (gen / "init.sh", gen / "AGENTS.md", evo / "init.sh", evo / "AGENTS.md", workflow / "SKILL.md"):
        if not source.is_file():
            raise InstallError(f"Missing source: {source}")
    gen_agents = required_agents(gen, "ascendc-kernel-*")
    evo_agents = required_agents(evo, "*-*")
    expected_evo = {"lingxi-evo", "lingxi-partial", "ops-evo", "ops-partial"}
    if GEN_AGENTS - {agent.stem for agent in gen_agents} or expected_evo - {agent.stem for agent in evo_agents}:
        raise InstallError("Missing required generation or evolution agent declarations")
    result: dict[str, Path] = {}
    origins: dict[str, list[str]] = {}
    for plugin, agents, local_first, exclude_triton in (
        (gen, gen_agents, False, True), (evo, evo_agents, True, False)
    ):
        names = list(frontmatter_skills(plugin / "AGENTS.md"))
        for agent in agents:
            names.extend(frontmatter_skills(agent, required=False))
        for name in dict.fromkeys(names):
            # The umbrella declaration also includes repository collaboration tools.
            # They are outside operator generation/evolution, even if listed by a role.
            if name.startswith("gitcode-"):
                continue
            if exclude_triton and "triton" in name.lower():
                continue
            source = source_skill(plugin, shared, name, local_first)
            if name in result and result[name] != source and tree_digest(result[name]) != tree_digest(source):
                raise InstallError(f"Cross-plugin skill collision {name}: {result[name]} versus {source}")
            result.setdefault(name, source)
            origins.setdefault(name, []).append(f"{plugin.name}:{source}")
    if "ascend-op-workflow" in result and tree_digest(result["ascend-op-workflow"]) != tree_digest(workflow):
        raise InstallError("Workflow skill collides with a vendor skill")
    case_generator = shared / "op-case-generator"
    if not (case_generator / "SKILL.md").is_file():
        raise InstallError(f"Missing workflow dependency: {case_generator}")
    if "op-case-generator" in result and tree_digest(result["op-case-generator"]) != tree_digest(case_generator):
        raise InstallError("op-case-generator collides with a vendor dependency")
    result["op-case-generator"] = case_generator
    origins.setdefault("op-case-generator", []).append(f"workflow:{case_generator}")
    packaged_skills(result, origins, workflow)
    metadata = {
        "skill_origins": origins,
        "vendor_contracts": {f"{plugin.name}/{name}": digest(plugin / name)
                             for plugin in (gen, evo) for name in ("init.sh", "AGENTS.md")},
        "vendor_agents": {agent.stem: {"source": str(agent), "sha256": digest(agent)}
                          for agent in gen_agents + evo_agents},
    }
    return result, metadata


def output_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def route_text(repo: Path | None, application: bool = False) -> bytes:
    if repo is None or application:
        dependency = (
            "The CANNBot application and its companion skills are installed for this task. "
            "The install manifest records their source and revisions. "
            "For a task that requires the workflow's legacy direct-invoke or evolution role templates, "
            "use an explicitly selected checkout that contains those templates. "
            if application else
            "Shape/workload preparation is available without CANNBot. When a stage needs CANNBot, "
            "reuse the task's known checkout or ask whether to install it or select an existing one. "
            "If installation is declined, continue independent steps and report the missing dependency. "
        )
        return (
            "# Ascend operator workflow for Codex\n\n"
            "Start with `.agents/skills/ascend-op-workflow/SKILL.md`. For MindIE entry, read "
            "its `references/mindie.md`. Codex executes generation and optimization by default; "
            "Claude is optional. Generation and optimization consume substantial tokens; "
            "recommend a regular coding model and medium effort.\n\n"
            "Default auto scope generates the first implementation directly, then runs lightweight acceptance: "
            "full correctness and the frozen 10 performance cases, at most 3 ultra-large. "
            "Deliver G when the target is met; enter optimization only when it is unmet, unless "
            "the user explicitly requests full scope. Do not preselect implementation structure; "
            "every optimization round needs causal analysis before further dispatch.\n\n"
            + dependency +
            "Read original CANNBot instructions and use available tools; do not modify CANNBot, "
            "register Claude agents in Codex, or assume Claude hooks run. "
            "Use the bundled scripts/cannbot and references/cannbot-execution.md with "
            "the selected external checkout; no separate local adapter package is required.\n"
        ).encode("utf-8")
    gen = repo / "plugins-official" / GEN / "AGENTS.md"
    evo = repo / "plugins-community" / EVO / "AGENTS.md"
    return (
        "# Ascend operator workflow for Codex\n\n"
        "Start with `.agents/skills/ascend-op-workflow/SKILL.md`. For MindIE entry read its "
        "`references/mindie.md`. Codex is the default executor; Claude is optional. Generation and "
        "optimization consume substantial tokens; recommend a regular coding model and medium effort. "
        "Keep the external CANNBot checkout unchanged. Use the workflow's stage and evidence rules. "
        "GitCode collaboration skills are outside this workflow's installation scope. "
        "For generation, read the source generation AGENTS.md below; for optimization, first read "
        "references/cannbot-execution.md in the installed workflow and use its bundled "
        "scripts/cannbot helpers with explicit source paths and the selected execution profile. "
        "The evolution AGENTS.md supplies native role references. These plugin roots have "
        "AGENTS.md entrypoints, not root SKILL.md files; "
        "do not invent a Skill() call for either plugin. Keep their roles and original agent names distinct.\n\n"
        f"- Generation instructions: `{gen}`\n"
        f"- Evolution instructions: `{evo}`\n\n"
        "Before generation, establish the workload, full case manifest, original baseline, oracle, "
        "device and timing protocol. Codex owns stages 0-4, including implementation selection and generation. Stages 5-7 may use Codex independently or Codex plus Claude. Codex may "
        "execute directly or supervise Claude in the verified task environment. For supervised "
        "execution, read `references/execution-modes.md` within the workflow skill, preserve the "
        "assigned executor, and verify submission, acknowledgement, execution and raw evidence. "
        "Do not start a duplicate worker or periodic monitoring without current authorization. "
        "For direct execution, use available Codex tools and the source AGENTS.md plus its "
        "`ascendc-kernel-architect`, `ascendc-kernel-design-reviewer`, "
        "`ascendc-kernel-developer` and `ascendc-kernel-reviewer` references. "
        "Generate AscendC directly using the Step 1-7 direct-invoke pipeline and its "
        "`workflows/task-prompts.md` templates. "
        "Default auto scope generates the first implementation directly, then runs lightweight acceptance: "
        "full correctness and the frozen 10 performance cases, at most 3 ultra-large. "
        "Record measured R/G evidence and run workflow.py decision: deliver G when the target is met; "
        "enter optimization only when it is unmet, unless the user explicitly requests full scope. "
        "Missing or conflicting measurements require acceptance work. Do not preselect kernel count, "
        "C/V splitting or intermediate GM layout. Every optimization round needs causal analysis "
        "and evidence-backed next hypotheses before further dispatch. "
        "Before optimization, freeze the fully correct G package and read the evolution AGENTS.md "
        "and the relevant `ops-evo`/`lingxi-evo` plus partial agent references. The original agent "
        "names and source hashes are in `.agents/ascend-op-workflow-install.json` under `vendor_agents`.\n\n"
        "Claude agents are references, not native Codex registrations. Invoke only tools actually "
        "available in this Codex task; do not invent a Skill() or agent call. Claude hooks are not "
        "installed or automatically executed by Codex. At each stage, explicitly inspect the "
        "documents and logs that vendor hooks would gate: design/contract, full correctness, "
        "measured performance, and the frozen G/O lineage. Use the workflow's `prepare`, `result`, "
        "and `verify` commands for task records; their schema checks do not prove that raw logs "
        "match claimed measurements.\n\n"
        "Remote generation or optimization still requires the full CANNBot source and its documented "
        "environment. Resolve source scripts and templates by their absolute paths and run with the "
        "task as the working directory so generated operators stay task-local. Resolve `workflows/`, "
        "`asc-devkit/`, hook and build resources from their documented source roots. This Windows skill snapshot "
        "does not install Linux asc-devkit/workflows/hooks or independently provide a compile-ready "
        "NPU environment.\n"
    ).encode("utf-8")


def plan(repo: Path | None, task: Path, workflow: Path) -> tuple[dict, dict]:
    repo = repo.resolve(strict=True) if repo else None
    task = task.resolve(strict=True)
    workflow = workflow.resolve(strict=True)
    if not task.is_dir():
        raise InstallError(f"Task directory is not a directory: {task}")
    skills, metadata = discover(repo, workflow)
    entries = {}
    for name, source in sorted(skills.items()):
        entries[f".agents/skills/{name}"] = {
            "kind": "tree", "source": str(source), "sha256": tree_digest(source)
        }
    route = route_text(repo, application="cannbot_revisions" in metadata)
    entries["AGENTS.md"] = {"kind": "file", "source": None,
                            "sha256": hashlib.sha256(route).hexdigest(), "data": route}
    manifest = {"schema": 1, "repo_root": str(repo) if repo else None, "cannbot_root": str(repo) if repo else None,
                "workflow_repo_root": str(PACKAGE.resolve(strict=True)), "task_dir": str(task),
                "workflow_skill": str(workflow), **metadata,
                "entries": {name: {key: value for key, value in item.items() if key != "data"}
                            for name, item in sorted(entries.items())}}
    entries[MANIFEST] = {"kind": "file", "source": None,
                         "sha256": hashlib.sha256(output_bytes(manifest)).hexdigest(),
                         "data": output_bytes(manifest)}
    return entries, manifest


def check(task: Path, entries: dict, manifest: dict) -> bool:
    record = task / MANIFEST
    if is_reparse(record):
        raise InstallError(f"Linked manifest is not allowed: {record}")
    for relative in entries:
        target = task / relative
        for parent in target.parents:
            if parent == task:
                break
            if is_reparse(parent) or (parent.exists() and not parent.is_dir()):
                raise InstallError(f"Unsafe destination parent: {parent}")
    if record.exists():
        if json.loads(record.read_text(encoding="utf-8")) != manifest:
            raise InstallError("Existing installer manifest differs; refusing update")
        for relative, item in entries.items():
            target = task / relative
            if is_reparse(target) or not target.exists():
                raise InstallError(f"Managed entry changed: {target}")
            actual = tree_digest(target) if item["kind"] == "tree" else digest(target)
            if actual != item["sha256"]:
                raise InstallError(f"Managed entry changed: {target}")
        return True
    for relative in entries:
        target = task / relative
        if target.exists() or is_reparse(target):
            raise InstallError(f"Existing unowned file or directory would be overwritten: {target}")
    return False


def install(task: Path, entries: dict) -> None:
    for relative, item in entries.items():
        if relative == MANIFEST:
            continue
        target = task / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if item["kind"] == "tree":
            shutil.copytree(filesystem_path(Path(item["source"])), filesystem_path(target),
                            symlinks=False, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            target.write_bytes(item["data"])
    record = task / MANIFEST
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_bytes(entries[MANIFEST]["data"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--cannbot-root", "--repo-root", dest="cannbot_root",
                        help="Use an existing checkout instead of fetching CANNBot master")
    source.add_argument("--workflow-only", action="store_true", help="Install workflow and shape only")
    parser.add_argument("--task-dir", required=True)
    parser.add_argument("--workflow-skill", help="Defaults to this package's skills/ascend-op-workflow")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        repo = Path(args.cannbot_root).resolve(strict=True) if args.cannbot_root else None
        raw_task = Path(args.task_dir)
        reject_reparse_chain(raw_task)
        task = raw_task.resolve(strict=True)
        workflow = (Path(args.workflow_skill) if args.workflow_skill else
                    PACKAGE / "skills/ascend-op-workflow")
        default_source = repo is None and not args.workflow_only
        checkout = task / CANNBOT_CHECKOUT
        if default_source:
            reject_reparse_chain(checkout)
            if checkout.exists():
                if not (checkout / ".git").exists():
                    raise InstallError(f"Invalid CANNBot checkout: {checkout}")
                repo = checkout
            elif args.apply:
                entries, manifest = plan(None, task, workflow)
                check(task, entries, manifest)
                if (task / MANIFEST).exists():
                    raise InstallError("Existing workflow-only install; use --workflow-only to verify it")
                clone_cannbot(checkout)
                repo = checkout
        if default_source and repo is not None:
            if (git(repo, "config", "--get", "remote.origin.url") != CANNBOT_URL or
                    git(repo, "rev-parse", "HEAD:" + CANNBOT_VENDOR) !=
                    git(repo / CANNBOT_VENDOR, "rev-parse", "HEAD")):
                raise InstallError(f"Unexpected CANNBot source in {repo}; use --cannbot-root to select a checkout")
        entries, manifest = plan(repo, task, workflow)
        installed = check(task, entries, manifest)
        if args.apply and not installed:
            install(task, entries)
            installed = True
        report = {"status": "installed" if installed else "dry-run",
                  "task_dir": str(task), "skills": len(entries) - 2,
                  "manifest": str(task / MANIFEST)}
        if default_source:
            report["cannbot"] = {"url": CANNBOT_URL, "branch": CANNBOT_BRANCH,
                                 "path": str(checkout), **manifest.get("cannbot_revisions", {})}
        elif manifest.get("cannbot_revisions"):
            report["cannbot"] = {"path": str(repo), **manifest["cannbot_revisions"]}
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0
    except (InstallError, OSError, json.JSONDecodeError) as exc:
        print(f"install_codex: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
