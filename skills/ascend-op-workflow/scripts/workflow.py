#!/usr/bin/env python3
"""Local, standard-library archive and evidence gates for operator handoffs.

This program never builds, benchmarks, invokes a kernel, or runs another command.
It checks the supplied evidence and preserves the referenced bytes for review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = 1
TARGETS = {"generation": 1.2, "optimization": 1.5}


class WorkflowError(ValueError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, sort_keys=True)
        stream.write("\n")


def read_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise WorkflowError(f"Missing or linked JSON file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowError(f"Invalid JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise WorkflowError(f"Expected JSON object: {path}")
    return value


def safe_source(path: Path, allow_link: bool = False) -> Path:
    path = path.absolute()
    if allow_link:
        path = path.resolve(strict=True)
    if not path.exists() or path.is_symlink():
        raise WorkflowError(f"Missing or linked input: {path}")
    for item in (path, *path.parents):
        if item.is_symlink():
            raise WorkflowError(f"Linked path is not allowed: {item}")
    if path.is_dir():
        for root, dirs, files in os.walk(path, followlinks=False):
            for name in dirs + files:
                entry = Path(root) / name
                if entry.is_symlink():
                    raise WorkflowError(f"Linked input is not allowed: {entry}")
    elif not path.is_file():
        raise WorkflowError(f"Expected regular file or directory: {path}")
    return path


def within(run: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise WorkflowError(f"Invalid archive path: {relative}")
    path = run / relative
    if not path.resolve().is_relative_to(run.resolve()):
        raise WorkflowError(f"Archive path escapes run: {relative}")
    item = path
    while item != run.parent:
        if item.is_symlink():
            raise WorkflowError(f"Linked archive path: {item}")
        item = item.parent
    return path


def file_manifest(root: Path, run: Path) -> dict[str, str]:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise WorkflowError(f"Linked archive entry: {path}")
        if path.is_file():
            result[path.relative_to(run).as_posix()] = digest(path)
    return result


def copy_inputs(sources: list[Path], destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    for number, source in enumerate(sources):
        source = safe_source(source)
        target = destination / f"{number:03d}-{source.name}"
        if source.is_dir():
            shutil.copytree(source, target, symlinks=False)
        else:
            shutil.copy2(source, target)


def load_run(run: Path) -> dict:
    run = safe_source(run)
    config = read_json(run / "run.json")
    if config.get("schema") != SCHEMA or config.get("mode") not in ("production", "rehearsal"):
        raise WorkflowError("Unsupported or invalid run configuration")
    verify(run)
    return config


def verify(run: Path) -> dict:
    run = safe_source(run)
    config = read_json(run / "run.json")
    manifest = config.get("files")
    if not isinstance(manifest, dict):
        raise WorkflowError("Run has no file manifest")
    package_ids = config.get("packages", {})
    handoff_ids = config.get("handoffs", {})
    preparation_ids = config.get("preparations", {})
    if not isinstance(package_ids, dict) or not isinstance(handoff_ids, dict) or not isinstance(preparation_ids, dict):
        raise WorkflowError("Invalid archive index")
    for identifier, meta in {**package_ids, **handoff_ids, **preparation_ids}.items():
        if not isinstance(identifier, str) or not isinstance(meta, dict):
            raise WorkflowError("Invalid archive index")
        files = meta.get("files")
        if not isinstance(files, dict):
            raise WorkflowError(f"Archive {identifier} has no file manifest")
        manifest = {**manifest, **files}
    for relative, expected in manifest.items():
        if not isinstance(expected, str) or len(expected) != 64:
            raise WorkflowError(f"Invalid archived checksum: {relative}")
        path = within(run, relative)
        if not path.is_file() or digest(path) != expected:
            raise WorkflowError(f"Missing or changed archived file: {relative}")
    identity = read_json(run / "inputs" / "identity.json")
    for key in ("mode", "input_kind", "case_ids", "targets", "optimization_plan"):
        if config.get(key) != identity.get(key):
            raise WorkflowError(f"Run identity changed: {key}")
    return config


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def save_index(run: Path, config: dict) -> None:
    temp = run / f"run-{uuid.uuid4().hex}.json"
    write_json(temp, config)
    os.replace(temp, run / "run.json")


def full_correctness(evidence: dict, config: dict) -> None:
    ids = evidence.get("case_ids")
    expected = config.get("case_ids")
    if (not isinstance(ids, list) or not isinstance(expected, list)
            or len(ids) != len(expected) or any(not isinstance(x, str) for x in ids)
            or set(ids) != set(expected)):
        raise WorkflowError("Evidence case_ids must equal the frozen full case manifest")
    correctness = evidence.get("correctness")
    checked = correctness.get("case_ids") if isinstance(correctness, dict) else None
    if (not isinstance(correctness, dict) or correctness.get("full") is not True
            or correctness.get("passed") is not True or not isinstance(checked, list)
            or len(checked) != len(expected) or any(not isinstance(x, str) for x in checked)
            or set(checked) != set(expected)):
        raise WorkflowError("Production requires passing full correctness for every frozen case")
    artifacts = evidence.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts or any(not isinstance(x, str) for x in artifacts):
        raise WorkflowError("Production evidence must cite existing source artifacts")


def target_for(config: dict, stage: str) -> float:
    key = "original_to_generation" if stage == "generation" else "generation_to_optimization"
    return config["targets"][key]


def prepare(args: argparse.Namespace) -> dict:
    run = Path(args.run).absolute()
    config = load_run(run)
    skill = safe_source(Path(args.skill), allow_link=True)
    if not skill.is_file():
        raise WorkflowError("Skill entry must be a file")
    sources = [skill]
    baseline = "original"
    route = "generation"
    evidence = None
    if args.stage == "generation":
        if args.candidate or args.reuse_evidence:
            raise WorkflowError("Generation preparation uses the frozen original input only")
    else:
        if not args.candidate or args.candidate not in config["packages"]:
            raise WorkflowError("Optimization preparation requires a frozen G package")
        baseline = args.candidate
        existing_baselines = {
            item["baseline_package"] for item in config["preparations"].values()
            if item["stage"] == "optimization"
        }
        if existing_baselines and existing_baselines != {baseline}:
            raise WorkflowError("Optimization G baseline is fixed for this run")
        valid_generation = any(
            item["stage"] == "generation" and item["candidate_package"] == baseline
            and (config["mode"] == "rehearsal" or
                 (item.get("mode") == "production" and item.get("status") in ("TARGET_MET", "TARGET_UNMET")))
            for item in config["handoffs"].values()
        )
        if valid_generation:
            if args.reuse_evidence:
                raise WorkflowError("Reuse evidence applies only when skipping generation")
            route = "rehearsal-generated" if config["mode"] == "rehearsal" else "generated"
        elif config["mode"] == "rehearsal":
            if args.reuse_evidence:
                raise WorkflowError("Rehearsal does not accept reuse evidence")
            route = "synthetic-g"
        elif config["input_kind"] == "ascendc" and args.reuse_evidence:
            route = "reuse-ascendc"
            if config["mode"] == "production":
                source = safe_source(Path(args.reuse_evidence))
                evidence = read_json(source)
                if evidence.get("provenance") != "validated" or evidence.get("synthetic") is True or evidence.get("candidate_package") != baseline:
                    raise WorkflowError("AscendC reuse requires validated, non-synthetic package evidence")
                full_correctness(evidence, config)
                sources.extend([source, *(safe_source(Path(x)) for x in evidence["artifacts"])])
        else:
            raise WorkflowError("Optimization requires a generation result or AscendC reuse validation")
        if config["mode"] == "production" and route == "reuse-ascendc" and evidence is None:
            raise WorkflowError("Production reuse requires --reuse-evidence")
    identifier = new_id("prepare")
    destination = run / "preparations" / identifier
    copy_inputs(sources, destination / "references")
    output = {
        "schema": SCHEMA, "stage": args.stage, "mode": config["mode"],
        "route": route, "baseline_package": baseline,
        "case_ids": config.get("case_ids"),
        "skill_entry": str(skill), "correctness": None,
        "speedup_geomean": None, "target_speedup": target_for(config, args.stage),
        "optimization_plan": config["optimization_plan"] if args.stage == "optimization" else None,
        "reuse_evidence": evidence, "created_at": now(),
    }
    write_json(destination / "prepare.json", output)
    config["preparations"][identifier] = {
        "stage": args.stage, "baseline_package": baseline,
        "route": route, "files": file_manifest(destination, run),
    }
    save_index(run, config)
    return {"preparation_id": identifier, "stage": args.stage, "baseline_package": baseline, "route": route, "path": str(destination / "prepare.json")}


def init(args: argparse.Namespace) -> dict:
    run = Path(args.run).absolute()
    if run.exists():
        raise WorkflowError(f"Run already exists: {run}")
    sources = [safe_source(Path(item)) for item in args.input]
    if (not math.isfinite(args.generation_target) or args.generation_target <= 0
            or not math.isfinite(args.optimization_target) or args.optimization_target <= 0
            or args.rounds < 1 or args.variants < 1):
        raise WorkflowError("Targets, rounds, and variants must be positive")
    if args.mode == "production" and not args.case_manifest:
        raise WorkflowError("Production init requires --case-manifest")
    case_ids = None
    if args.case_manifest:
        manifest_source = safe_source(Path(args.case_manifest))
        case_ids = read_json(manifest_source).get("case_ids")
        if (not isinstance(case_ids, list) or not case_ids
                or any(not isinstance(x, str) or not x for x in case_ids)
                or len(case_ids) != len(set(case_ids))):
            raise WorkflowError("Case manifest requires nonempty unique case_ids")
    if any(run == src or run.is_relative_to(src) for src in sources if src.is_dir()):
        raise WorkflowError("Run cannot be created inside an input directory")
    run.mkdir(parents=True, exist_ok=False)
    original = run / "packages" / "original" / "source"
    copy_inputs(sources, original)
    files = file_manifest(original, run)
    if args.case_manifest:
        case_target = run / "inputs" / "case-manifest.json"
        case_target.parent.mkdir()
        shutil.copy2(manifest_source, case_target)
        files.update(file_manifest(case_target.parent, run))
    config = {
        "schema": SCHEMA,
        "name": args.name,
        "input_kind": args.input_kind,
        "mode": args.mode,
        "created_at": now(),
        "targets": {"original_to_generation": args.generation_target, "generation_to_optimization": args.optimization_target},
        "optimization_plan": {"rounds": args.rounds, "candidates_per_round": args.variants},
        "inputs": [str(src) for src in sources],
        "case_ids": case_ids,
        "files": files,
        "packages": {"original": {"source": "input", "files": {}}},
        "handoffs": {},
        "preparations": {},
    }
    identity = {key: config[key] for key in ("mode", "input_kind", "case_ids", "targets", "optimization_plan")}
    write_json(run / "inputs" / "identity.json", identity)
    config["files"].update(file_manifest(run / "inputs", run))
    write_json(run / "run.json", config)
    return {"run": str(run), "original_package": "original", "mode": args.mode}


def freeze(args: argparse.Namespace) -> dict:
    run = Path(args.run).absolute()
    config = load_run(run)
    source = safe_source(Path(args.package))
    if (source == run or (source.is_dir() and run.is_relative_to(source))
            or source.is_relative_to(run / "packages")
            or source.is_relative_to(run / "handoffs")
            or source.is_relative_to(run / "preparations")):
        raise WorkflowError("Package source cannot be inside the immutable archive")
    identifier = new_id("package")
    target = run / "packages" / identifier / "source"
    copy_inputs([source], target)
    files = file_manifest(target, run)
    config["packages"][identifier] = {"source": str(source), "files": files, "created_at": now()}
    # Replace the index only after the new immutable archive exists.
    temp = run / f"run-{uuid.uuid4().hex}.json"
    write_json(temp, config)
    os.replace(temp, run / "run.json")
    return {"package_id": identifier, "files": len(files)}


def measured_evidence(evidence: dict, stage: str, candidate: str, config: dict) -> tuple[float, float]:
    if evidence.get("provenance") != "measured" or evidence.get("synthetic") is True:
        raise WorkflowError("Production requires measured, non-synthetic evidence")
    measurement = evidence.get("measurement")
    if (not isinstance(measurement, dict) or measurement.get("unit") != "us"
            or any(not isinstance(measurement.get(key), str) or not measurement[key].strip()
                   for key in ("metric", "protocol_id", "paired_run_id", "device"))):
        raise WorkflowError("Production measurement needs metric, unit=us, protocol_id, paired_run_id, and device")
    if evidence.get("candidate_package") != candidate:
        raise WorkflowError("Evidence candidate_package differs from selected package")
    baseline = evidence.get("baseline_package")
    if not isinstance(baseline, str) or baseline not in config["packages"] or baseline == candidate:
        raise WorkflowError("Evidence baseline_package must be a distinct frozen package")
    if stage == "generation" and baseline != "original":
        raise WorkflowError("Generation must compare against original")
    full_correctness(evidence, config)
    ids = evidence["case_ids"]
    baseline_us, candidate_us = evidence.get("baseline_us"), evidence.get("candidate_us")
    if not isinstance(baseline_us, dict) or not isinstance(candidate_us, dict) or set(baseline_us) != set(ids) or set(candidate_us) != set(ids):
        raise WorkflowError("Measured timing maps must cover exactly case_ids")
    def timing(value: object) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise WorkflowError("Measurements must be finite positive microseconds")
        return float(value)
    ratios = [timing(baseline_us[x]) / timing(candidate_us[x]) for x in ids]
    speedup = math.exp(sum(math.log(r) for r in ratios) / len(ratios))
    return speedup, target_for(config, stage)


def record_result(args: argparse.Namespace) -> dict:
    run = Path(args.run).absolute()
    config = load_run(run)
    preparation = config["preparations"].get(args.preparation)
    if not preparation or preparation["stage"] != args.stage:
        raise WorkflowError("Result requires a matching preparation ID")
    if args.candidate not in config["packages"] or args.candidate == "original":
        raise WorkflowError("Select a frozen candidate package")
    if args.stage == "optimization" and args.candidate == preparation["baseline_package"]:
        raise WorkflowError("Optimization result must use a new candidate package")
    skill = safe_source(Path(args.skill), allow_link=True)
    if not skill.is_file():
        raise WorkflowError("Skill entry must be a file")
    evidence = None
    speedup = target = None
    sources = [skill]
    if config["mode"] == "production":
        if not args.evidence:
            raise WorkflowError("Production handoff requires --evidence")
        evidence_path = safe_source(Path(args.evidence))
        evidence = read_json(evidence_path)
        speedup, target = measured_evidence(evidence, args.stage, args.candidate, config)
        if evidence["baseline_package"] != preparation["baseline_package"]:
            raise WorkflowError("Evidence baseline differs from preparation baseline")
        sources.append(evidence_path)
        for name in evidence["artifacts"]:
            sources.append(safe_source(Path(name)))
    elif args.evidence:
        raise WorkflowError("Rehearsal handoff does not accept evidence")
    baseline_package = preparation["baseline_package"]
    identifier = new_id("handoff")
    target_dir = run / "handoffs" / identifier
    copy_inputs(sources, target_dir / "references")
    status = "REHEARSAL" if evidence is None else ("TARGET_MET" if speedup >= target else "TARGET_UNMET")
    output = {
        "schema": SCHEMA,
        "stage": args.stage,
        "mode": config["mode"],
        "status": status,
        "candidate_package": args.candidate,
        "baseline_package": baseline_package,
        "preparation_id": args.preparation,
        "skill_entry": str(skill),
        "evidence": evidence,
        "correctness": None if evidence is None else evidence["correctness"],
        "speedup_geomean": speedup,
        "target_speedup": target_for(config, args.stage),
        "optimization_plan": config["optimization_plan"] if args.stage == "optimization" else None,
        "created_at": now(),
    }
    write_json(target_dir / "handoff.json", output)
    files = file_manifest(target_dir, run)
    config["handoffs"][identifier] = {"stage": args.stage, "candidate_package": args.candidate, "files": files, "status": status, "mode": config["mode"]}
    save_index(run, config)
    return {"result_id": identifier, "status": status, "speedup_geomean": speedup, "target_speedup": target_for(config, args.stage), "path": str(target_dir / "handoff.json")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("init")
    p.add_argument("--run", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--input-kind", choices=["ascendc", "triton", "torch"], required=True)
    p.add_argument("--mode", choices=["production", "rehearsal"], required=True)
    p.add_argument("--input", action="append", required=True)
    p.add_argument("--case-manifest")
    p.add_argument("--generation-target", type=float, default=1.2)
    p.add_argument("--optimization-target", type=float, default=1.5)
    p.add_argument("--rounds", type=int, default=5)
    p.add_argument("--variants", type=int, default=5)
    p = sub.add_parser("freeze")
    p.add_argument("--run", required=True)
    p.add_argument("--package", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--run", required=True)
    p.add_argument("--stage", choices=list(TARGETS), required=True)
    p.add_argument("--skill", required=True)
    p.add_argument("--candidate")
    p.add_argument("--reuse-evidence")
    p = sub.add_parser("result")
    p.add_argument("--run", required=True)
    p.add_argument("--stage", choices=list(TARGETS), required=True)
    p.add_argument("--preparation", required=True)
    p.add_argument("--candidate", required=True)
    p.add_argument("--skill", required=True)
    p.add_argument("--evidence")
    for name in ("inspect", "verify"):
        p = sub.add_parser(name)
        p.add_argument("--run", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            result = init(args)
        elif args.command == "freeze":
            result = freeze(args)
        elif args.command == "prepare":
            result = prepare(args)
        elif args.command == "result":
            result = record_result(args)
        elif args.command == "inspect":
            config = load_run(Path(args.run).absolute())
            result = {k: v for k, v in config.items() if k != "files"}
        else:
            config = verify(Path(args.run).absolute())
            result = {"verified": True, "packages": len(config["packages"]), "preparations": len(config["preparations"]), "results": len(config["handoffs"])}
    except (WorkflowError, OSError) as exc:
        print(f"workflow: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
