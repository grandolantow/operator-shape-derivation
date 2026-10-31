#!/usr/bin/env python3
"""Local, standard-library archive and evidence gates for operator handoffs.

[Role] Archive evidence and link caller-observed execution references.
[Invariants] Fixed run/G identity; execution links never dispatch or own job state.
[Timeouts & Locks] No subprocess or network waits; one parent writer per run.
[Side-Effect Policy] Write only the selected run archive and execution-links.json.
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


def read_run(run: Path) -> dict:
    # Metadata queries do not walk packages or hash archived evidence.
    config = read_json(within(run, "run.json"))
    if config.get("schema") != SCHEMA or config.get("mode") not in ("production", "rehearsal"):
        raise WorkflowError("Unsupported or invalid run configuration")
    return config


def load_run(run: Path) -> dict:
    config = read_run(run)
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
    review_ids = config.get("round_reviews", {})
    if not all(isinstance(x, dict) for x in (package_ids, handoff_ids, preparation_ids, review_ids)):
        raise WorkflowError("Invalid archive index")
    for identifier, meta in {**package_ids, **handoff_ids, **preparation_ids, **review_ids}.items():
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
    for identifier, meta in review_ids.items():
        relative = f"round-reviews/{identifier}/review.json"
        if relative not in meta["files"]:
            # Historical review archives remain readable, but cannot prove order.
            continue
        receipt = read_json(within(run, relative))
        source = receipt.get("record")
        if source not in meta["files"]:
            raise WorkflowError("Round review source is not in its frozen manifest")
        review = read_json(within(run, source))
        if (receipt.get("round") != review.get("round")
                or receipt.get("next_round_ready") is not bool(review.get("next_round_candidates"))
                or any(meta.get(key) != receipt.get(key)
                       for key in ("round", "sequence", "next_round_ready"))):
            raise WorkflowError("Round review index differs from its frozen record")
    identity = read_json(run / "inputs" / "identity.json")
    for key in ("mode", "input_kind", "case_ids", "targets", "optimization_plan"):
        if config.get(key) != identity.get(key):
            raise WorkflowError(f"Run identity changed: {key}")
    for key in ("performance_case_ids", "performance_selection", "round_review_required", "stage_scope"):
        if (key in config) != (key in identity) or config.get(key) != identity.get(key):
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


def performance_fields(manifest: dict, full_ids: list[str]) -> dict:
    """Validate an explicitly selected performance set without shrinking correctness."""
    if "performance_case_ids" not in manifest:
        if "performance_selection" in manifest:
            raise WorkflowError("performance_selection requires performance_case_ids")
        return {}
    ids = manifest["performance_case_ids"]
    if (not isinstance(ids, list) or len(ids) != 10
            or any(not isinstance(x, str) for x in ids)
            or len(set(ids)) != 10 or not set(ids).issubset(full_ids)):
        raise WorkflowError("Performance set requires exactly 10 unique full-case IDs")
    selection = manifest.get("performance_selection")
    if not isinstance(selection, dict) or selection.get("policy") != "fixed10-v1":
        raise WorkflowError("Explicit performance set requires fixed10-v1 selection")
    large = selection.get("ultra_large_case_ids")
    if (not isinstance(large, list) or any(not isinstance(x, str) for x in large)
            or len(set(large)) != len(large) or len(large) > 3 or not set(large).issubset(ids)):
        raise WorkflowError("At most 3 selected performance cases may be ultra-large")
    classification = selection.get("classification")
    if not isinstance(classification, dict) or not classification.get("definition"):
        raise WorkflowError("Performance selection needs a frozen scale definition")
    cases = classification.get("cases")
    if (not isinstance(cases, dict) or set(cases) != set(full_ids)
            or any(not isinstance(v, dict) or not isinstance(v.get("ultra_large"), bool)
                   for v in cases.values())):
        raise WorkflowError("Scale classification must cover every full correctness case")
    if set(large) != {x for x in ids if cases[x]["ultra_large"]}:
        raise WorkflowError("Ultra-large case declarations differ from frozen classification")
    return {"performance_case_ids": ids, "performance_selection": selection}


def check_round(config: dict, next_round: int, *, for_review: bool = False) -> dict:
    if not 1 <= next_round <= config["optimization_plan"]["rounds"]:
        raise WorkflowError("Round is outside the frozen optimization plan")
    reviews = [dict(item, review_id=identifier)
               for identifier, item in config.get("round_reviews", {}).items()]
    if any(f"round-reviews/{item['review_id']}/review.json" not in item["files"]
           for item in reviews):
        raise WorkflowError("Legacy round reviews lack frozen ordering receipts; inspect before resuming")
    if config.get("round_review_required"):
        if not for_review and any(item["round"] >= next_round for item in reviews):
            raise WorkflowError("Completed rounds cannot be reopened")
        latest_by_round = {}
        for item in sorted(reviews, key=lambda item: item["sequence"]):
            latest_by_round[item["round"]] = item
        if any(not item["next_round_ready"] and
               (item["round"] < next_round or not for_review)
               for item in latest_by_round.values()):
            raise WorkflowError("A terminal round review prevents further dispatch")
        if for_review and any(item["round"] > next_round for item in reviews):
            raise WorkflowError("Cannot revise a round after a later round was reviewed")
    matches = [item for item in reviews
               if item["round"] == next_round - 1]
    if config.get("round_review_required") and next_round > 1 and not matches:
        raise WorkflowError("Previous round analysis is required before the next round")
    latest = max(matches, key=lambda item: item["sequence"]) if matches else None
    if latest and not latest["next_round_ready"]:
        raise WorkflowError("Previous round review records a stop, not a next-round plan")
    return {"next_round": next_round, "previous_review": latest}


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
        if config.get("stage_scope") == "generation_only":
            raise WorkflowError("generation_only run cannot prepare optimization")
        if config.get("round_review_required") and args.round is None:
            raise WorkflowError("Review-gated optimization requires explicit --round")
        round_number = 1 if args.round is None else args.round
        round_gate = check_round(config, round_number)
        if not args.candidate or args.candidate not in config["packages"]:
            raise WorkflowError("Optimization preparation requires a frozen G package")
        baseline = args.candidate
        existing_baselines = {
            item["baseline_package"] for item in archived_preparations(run, config)
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
        if config.get("stage_scope") == "auto" and config["mode"] == "production":
            decision = generation_decision(run, config, baseline)
            if decision["next_action"] != "optimize":
                raise WorkflowError(f"Auto optimization blocked: {decision['next_action']}; record measured R/G acceptance first if needed")
            valid_generation = True
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
    for key in ("performance_case_ids", "performance_selection"):
        if key in config:
            output[key] = config[key]
    if args.stage == "optimization":
        output.update(round=round_number, round_gate=round_gate)
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
    performance = {}
    if args.case_manifest:
        manifest_source = safe_source(Path(args.case_manifest))
        case_manifest = read_json(manifest_source)
        case_ids = case_manifest.get("case_ids")
        if (not isinstance(case_ids, list) or not case_ids
                or any(not isinstance(x, str) or not x for x in case_ids)
                or len(case_ids) != len(set(case_ids))):
            raise WorkflowError("Case manifest requires nonempty unique case_ids")
        performance = performance_fields(case_manifest, case_ids)
    if args.mode == "production" and not performance:
        raise WorkflowError("New production runs require a frozen fixed10-v1 performance selection")
    if args.optimization_seconds is not None and args.optimization_seconds <= 0:
        raise WorkflowError("Optimization time budget must be positive")
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
    config.update(performance)
    if args.optimization_seconds is not None:
        config["optimization_plan"]["budget_seconds"] = args.optimization_seconds
    if args.require_round_reviews or args.stage_scope == "auto" or args.mode == "production":
        config["round_review_required"] = True
    config["stage_scope"] = args.stage_scope
    identity = {key: config[key] for key in ("mode", "input_kind", "case_ids", "targets", "optimization_plan")}
    identity.update({key: config[key] for key in
                     ("performance_case_ids", "performance_selection", "round_review_required", "stage_scope")
                     if key in config})
    (run / "inputs").mkdir(exist_ok=True)
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
    ids = config.get("performance_case_ids", config["case_ids"])
    if "performance_case_ids" in config:
        declared = evidence.get("performance_case_ids")
        if (not isinstance(declared, list) or len(declared) != len(ids)
                or any(not isinstance(x, str) for x in declared) or set(declared) != set(ids)):
            raise WorkflowError("Evidence performance_case_ids must equal the frozen performance set")
    baseline_us, candidate_us = evidence.get("baseline_us"), evidence.get("candidate_us")
    if not isinstance(baseline_us, dict) or not isinstance(candidate_us, dict) or set(baseline_us) != set(ids) or set(candidate_us) != set(ids):
        raise WorkflowError("Measured timing maps must cover exactly the frozen performance IDs")
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
    metadata = config["preparations"].get(args.preparation)
    relative = f"preparations/{args.preparation}/prepare.json"
    if not metadata or relative not in metadata["files"]:
        raise WorkflowError("Result requires a matching preparation ID")
    preparation = read_json(within(run, relative))
    if preparation["stage"] != args.stage:
        raise WorkflowError("Result requires a matching preparation ID")
    if args.candidate not in config["packages"] or args.candidate == "original":
        raise WorkflowError("Select a frozen candidate package")
    if args.stage == "optimization" and args.candidate == preparation["baseline_package"]:
        raise WorkflowError("Optimization result must use a new candidate package")
    if args.stage == "generation":
        # Reject a changed G or invalid prior acceptance before any archive writes.
        generation_decision(run, config, args.candidate)
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
    for key in ("performance_case_ids", "performance_selection", "stage_scope"):
        if key in config:
            output[key] = config[key]
    write_json(target_dir / "handoff.json", output)
    files = file_manifest(target_dir, run)
    config["handoffs"][identifier] = {"stage": args.stage, "candidate_package": args.candidate, "files": files, "status": status, "mode": config["mode"]}
    save_index(run, config)
    result = {"result_id": identifier, "status": status, "speedup_geomean": speedup, "target_speedup": target_for(config, args.stage), "path": str(target_dir / "handoff.json")}
    if args.stage == "generation":
        result["decision"] = generation_decision(run, config, args.candidate)
    return result


def archived_preparations(run: Path, config: dict) -> list[dict]:
    records = []
    for identifier, metadata in config["preparations"].items():
        relative = f"preparations/{identifier}/prepare.json"
        if relative not in metadata["files"]:
            raise WorkflowError("Preparation record is not in its frozen manifest")
        records.append(read_json(within(run, relative)))
    return records


def generation_decision(run: Path, config: dict, candidate: str) -> dict:
    """Route only from hash-verified archived acceptance evidence for this G."""
    if candidate not in config["packages"] or candidate == "original":
        raise WorkflowError("Decision requires a distinct frozen G package")
    baseline = {item["baseline_package"] for item in archived_preparations(run, config)
                if item["stage"] == "optimization"}
    if baseline and baseline != {candidate}:
        raise WorkflowError("Optimization G baseline is fixed for this run")
    accepted = []
    for identifier, metadata in config["handoffs"].items():
        relative = f"handoffs/{identifier}/handoff.json"
        if relative not in metadata["files"]:
            raise WorkflowError("Decision requires a manifested handoff record")
        handoff = read_json(within(run, relative))
        if handoff.get("stage") != "generation" or handoff.get("candidate_package") != candidate:
            continue
        if config["mode"] != "production":
            continue
        if handoff.get("mode") != "production":
            raise WorkflowError("Generation acceptance mode differs from run")
        speedup, target = measured_evidence(handoff.get("evidence") or {}, "generation", candidate, config)
        preparation_id = handoff.get("preparation_id")
        preparation_metadata = config["preparations"].get(preparation_id)
        preparation_relative = f"preparations/{preparation_id}/prepare.json"
        if not preparation_metadata or preparation_relative not in preparation_metadata["files"]:
            raise WorkflowError("Generation acceptance requires its frozen preparation")
        preparation = read_json(within(run, preparation_relative))
        if (preparation.get("stage") != "generation"
                or preparation.get("mode") != config["mode"]
                or preparation.get("baseline_package") != "original"
                or handoff.get("baseline_package") != preparation.get("baseline_package")
                or handoff["evidence"].get("baseline_package") != handoff.get("baseline_package")):
            raise WorkflowError("Generation acceptance baseline/preparation binding differs")
        accepted.append((identifier, speedup, target))
    scope = config.get("stage_scope", "full")
    output = {"stage_scope": scope, "candidate_package": candidate,
              "correctness_status": "UNVERIFIED", "performance_status": "UNMEASURED",
              "next_action": "acceptance_required", "acceptance_result_ids": []}
    if not accepted:
        return output
    # Multiple paired acceptances may disagree; never choose a convenient pass.
    outcomes = {speedup >= target for _, speedup, target in accepted}
    output["correctness_status"] = "FULL_PASS"
    output["acceptance_result_ids"] = [identifier for identifier, _, _ in accepted]
    output["target_speedup"] = target_for(config, "generation")
    if len(outcomes) != 1:
        output.update(performance_status="CONFLICTING", next_action="acceptance_required")
        return output
    met = outcomes.pop()
    output["performance_status"] = "TARGET_MET" if met else "TARGET_UNMET"
    output["next_action"] = ("deliver_G" if scope == "generation_only" or (scope == "auto" and met)
                             else "optimize")
    return output


def record_round_review(args: argparse.Namespace) -> dict:
    run = Path(args.run).absolute()
    config = load_run(run)
    source = safe_source(Path(args.record))
    review = read_json(source)
    number = review.get("round")
    if isinstance(number, bool) or not isinstance(number, int):
        raise WorkflowError("Round review requires an integer round")
    if config.get("stage_scope") == "generation_only":
        raise WorkflowError("generation_only run cannot record optimization reviews")
    check_round(config, number, for_review=True)
    candidates = review.get("candidates")
    width = config["optimization_plan"]["candidates_per_round"]
    if not isinstance(candidates, list) or len(candidates) != width:
        raise WorkflowError("Round review must account for every candidate slot")
    ids, sources = set(), [source]
    perf_ids = set(config.get("performance_case_ids", config["case_ids"]) or [])
    statuses = {"evaluated", "precision_failed", "build_failed", "timeout", "cancelled", "static_rejected"}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise WorkflowError("Invalid candidate review")
        identifier = candidate.get("candidate_id")
        if not isinstance(identifier, str) or not identifier.strip() or identifier in ids:
            raise WorkflowError("Round candidate IDs must be nonempty and unique")
        ids.add(identifier)
        if candidate.get("status") not in statuses:
            raise WorkflowError("Every candidate needs a terminal status")
        artifacts = candidate.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise WorkflowError("Every candidate analysis must cite raw evidence")
        sources.extend(safe_source(Path(p)) for p in artifacts if isinstance(p, str))
        if any(not isinstance(p, str) for p in artifacts):
            raise WorkflowError("Invalid round artifact path")
        analysis = candidate.get("analysis")
        if not isinstance(analysis, dict) or analysis.get("status") not in {"confirmed", "hypothesis", "unknown"}:
            raise WorkflowError("Analysis status must be confirmed, hypothesis or unknown")
        for field in ("observations", "explanation", "next_experiment", "expected_observation"):
            if not isinstance(analysis.get(field), str) or not analysis[field].strip():
                raise WorkflowError(f"Candidate analysis requires {field}")
        slow_cases = analysis.get("slow_cases")
        if not isinstance(slow_cases, list) or (candidate["status"] == "evaluated" and not slow_cases):
            raise WorkflowError("Evaluated candidates require slow-case evidence")
        seen = set()
        for item in slow_cases:
            case_id = item.get("case_id") if isinstance(item, dict) else None
            if not isinstance(case_id, str) or case_id not in perf_ids or case_id in seen:
                raise WorkflowError("Slow-case IDs must be unique frozen performance IDs")
            seen.add(case_id)
            for key in ("baseline_us", "candidate_us"):
                value = item.get(key)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                    raise WorkflowError("Slow-case timing must be finite positive microseconds")
    next_candidates = review.get("next_round_candidates")
    if not isinstance(next_candidates, list):
        raise WorkflowError("Round review requires next_round_candidates")
    stop = review.get("stop_reason")
    if number == config["optimization_plan"]["rounds"] or stop:
        if next_candidates or (stop is not None and (not isinstance(stop, str) or not stop.strip())):
            raise WorkflowError("Stopped/final round must not schedule further candidates")
    else:
        if len(next_candidates) != width:
            raise WorkflowError("Next round requires one evidence-backed hypothesis per slot")
        for proposal in next_candidates:
            if not isinstance(proposal, dict):
                raise WorkflowError("Invalid next-round proposal")
            for field in ("hypothesis_id", "mechanism_change", "rationale", "falsifier"):
                if not isinstance(proposal.get(field), str) or not proposal[field].strip():
                    raise WorkflowError(f"Next-round proposal requires {field}")
            parents = proposal.get("source_candidate_ids")
            expected = proposal.get("expected_case_ids")
            if (not isinstance(parents, list) or not parents or any(not isinstance(x, str) for x in parents)
                    or not set(parents).issubset(ids)
                    or not isinstance(expected, list) or not expected
                    or any(not isinstance(x, str) for x in expected) or not set(expected).issubset(perf_ids)):
                raise WorkflowError("Hypotheses must reference current evidence and expected performance cases")
    identifier = new_id("round-review")
    target = run / "round-reviews" / identifier
    copy_inputs(sources, target / "references")
    reviews = config.setdefault("round_reviews", {})
    sequence = max((item["sequence"] for item in reviews.values()), default=0) + 1
    metadata = {"round": number, "sequence": sequence, "next_round_ready": bool(next_candidates)}
    write_json(target / "review.json", dict(metadata,
               record=(target / "references" / f"000-{source.name}").relative_to(run).as_posix()))
    metadata["files"] = file_manifest(target, run)
    reviews[identifier] = metadata
    save_index(run, config)
    return {"review_id": identifier, "round": number, "next_round_ready": bool(next_candidates), "path": str(target)}


def execution_links(run: Path) -> dict:
    path = within(run, "execution-links.json")
    if not path.exists():
        return {"parent_run": str(run), "executions": []}
    value = read_json(path)
    if value.get("parent_run") != str(run):
        raise WorkflowError("Execution links belong to another parent run")
    return value


def link_execution(args: argparse.Namespace) -> dict:
    run = Path(args.run).resolve(strict=True)
    config = read_run(run)
    if args.preparation not in config["preparations"]:
        raise WorkflowError("Preparation does not belong to this parent run")
    if args.result:
        if args.result not in config["handoffs"]:
            raise WorkflowError("Result does not belong to this parent run")
        handoff = read_json(within(run, f"handoffs/{args.result}/handoff.json"))
        if handoff["preparation_id"] != args.preparation:
            raise WorkflowError("Result belongs to another preparation")
    value = execution_links(run)
    entry = next((item for item in value["executions"] if item["job_id"] == args.job_id), None)
    is_new = entry is None
    if is_new:
        entry = {"preparation_id": args.preparation, "job_id": args.job_id,
                 "endpoint": args.endpoint, "container": args.container,
                 "executor": args.executor or "codex", "claude_session_id": None,
                 "evo_dir": None, "artifacts": [], "result_id": None}
    additions = {"preparation_id": args.preparation, "endpoint": args.endpoint,
                 "container": args.container, "executor": args.executor,
                 "model": args.model, "effort": args.effort,
                 "claude_session_id": args.claude_session, "result_id": args.result}
    if args.evo_dir:
        evo = Path(args.evo_dir).resolve(strict=True)
        if not evo.is_dir():
            raise WorkflowError("Evolution path must be an existing directory")
        additions["evo_dir"] = str(evo)
    # Older project records have no executor field; preserve their actual identity.
    executor = args.executor or entry.get("executor") or ("claude" if entry.get("claude_session_id") else "codex")
    if args.claude_session and executor != "claude":
        raise WorkflowError("Claude session requires --executor claude")
    for key, supplied in additions.items():
        if supplied is not None:
            if entry.get(key) is not None and entry[key] != supplied:
                raise WorkflowError(f"Existing job has a different {key}")
            entry[key] = supplied
    for raw in args.artifact:
        source = Path(raw).resolve(strict=True)
        if not source.is_file() and not source.is_dir():
            raise WorkflowError(f"Raw artifact must be a file or directory: {source}")
        if str(source) not in entry["artifacts"]:
            entry["artifacts"].append(str(source))
    if is_new:
        value["executions"].append(entry)
    temporary = run / f"execution-links-{uuid.uuid4().hex}.json"
    write_json(temporary, value)
    os.replace(temporary, within(run, "execution-links.json"))
    return value


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
    p.add_argument("--optimization-seconds", type=int)
    p.add_argument("--require-round-reviews", action="store_true")
    p.add_argument("--stage-scope", choices=["auto", "full", "generation_only"], default="auto")
    p = sub.add_parser("freeze")
    p.add_argument("--run", required=True)
    p.add_argument("--package", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--run", required=True)
    p.add_argument("--stage", choices=list(TARGETS), required=True)
    p.add_argument("--skill", required=True)
    p.add_argument("--candidate")
    p.add_argument("--reuse-evidence")
    p.add_argument("--round", type=int)
    p = sub.add_parser("result")
    p.add_argument("--run", required=True)
    p.add_argument("--stage", choices=list(TARGETS), required=True)
    p.add_argument("--preparation", required=True)
    p.add_argument("--candidate", required=True)
    p.add_argument("--skill", required=True)
    p.add_argument("--evidence")
    p = sub.add_parser("link", help="record an actual tool job receipt; never submit work")
    p.add_argument("--run", required=True)
    p.add_argument("--preparation", required=True)
    p.add_argument("--job-id", required=True)
    p.add_argument("--endpoint", required=True)
    p.add_argument("--container", required=True)
    p.add_argument("--executor", choices=["codex", "claude"])
    p.add_argument("--model")
    p.add_argument("--effort")
    p.add_argument("--claude-session")
    p.add_argument("--evo-dir")
    p.add_argument("--artifact", action="append", default=[])
    p.add_argument("--result")
    p = sub.add_parser("round-review", help="archive per-candidate diagnoses and next hypotheses")
    p.add_argument("--run", required=True)
    p.add_argument("--record", required=True)
    p = sub.add_parser("round-check", help="verify the previous analysis before selecting a new round")
    p.add_argument("--run", required=True)
    p.add_argument("--next-round", required=True, type=int)
    p = sub.add_parser("decision", help="route from verified frozen generation acceptance")
    p.add_argument("--run", required=True)
    p.add_argument("--candidate", required=True)
    for name in ("inspect", "verify", "show"):
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
        elif args.command == "link":
            result = link_execution(args)
        elif args.command == "decision":
            run = Path(args.run).absolute()
            result = generation_decision(run, load_run(run), args.candidate)
        elif args.command == "round-review":
            result = record_round_review(args)
        elif args.command == "round-check":
            config = load_run(Path(args.run).absolute())
            if config.get("stage_scope") == "generation_only":
                raise WorkflowError("generation_only run cannot enter optimization")
            result = check_round(config, args.next_round)
        elif args.command == "show":
            run = Path(args.run).resolve(strict=True)
            read_run(run)
            result = execution_links(run)
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
