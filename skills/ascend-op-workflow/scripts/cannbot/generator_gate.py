#!/usr/bin/env python3
"""Run explicit documentation/precision gates against a read-only CANNBot checkout.

The external hooks are loaded as libraries; no automatic hooks are registered.
All gate state and validation logs belong to the supplied task workspace.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

PLUGIN_RELATIVE = Path("plugins-community/tilelang2ascendc-ops-generator")
SCRIPTS = {
    "validate_tilelang_impl.py": ("tilelang2ascend-tilelang-designer", "ast"),
    "validate_ascendc_impl.py": ("tilelang2ascend-translator", "ast"),
    "verification_tilelang.py": ("tilelang2ascend-tilelang-designer", "tilelang"),
    "verification_ascendc.py": ("tilelang2ascend-translator", "ascendc"),
    "evaluate_ascendc.sh": ("tilelang2ascend-translator", "ascendc"),
}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def modules(workspace, cannbot_root=None):
    source = cannbot_root or os.environ.get("CANNBOT_SOURCE_ROOT")
    if not source:
        raise ValueError("Provide --cannbot-root or CANNBOT_SOURCE_ROOT")
    root = Path(source).resolve(strict=True)
    workspace = workspace.resolve()
    if workspace.is_relative_to(root) or root.is_relative_to(workspace):
        raise ValueError("Gate workspace and read-only CANNBot checkout must be separate")
    plugin = root / PLUGIN_RELATIVE
    hook_files = [plugin / "hooks" / name for name in ("doc_gate.py", "skill_script_hook.py")]
    source_identity = {"root": str(root), "hooks": {str(p.relative_to(root)): sha256(p) for p in hook_files}}
    state = workspace / ".cannbot/gates"
    if not within(state.resolve(), workspace):
        raise ValueError("Gate state path escapes workspace")
    state.mkdir(parents=True, exist_ok=True)
    for state_file in state.glob("*.json"):
        if not within(state_file.resolve(), workspace):
            raise ValueError("Gate state file escapes workspace")
        if not isinstance(json.loads(state_file.read_text(encoding="utf-8")), dict):
            raise ValueError("Gate state must be a JSON object")
    doc = load_module("cannbot_doc_gate", hook_files[0])
    hook = load_module("cannbot_script_gate", hook_files[1])
    hook._workflow_plugin = plugin
    hook._workflow_source = source_identity
    doc.PROJECT_ROOT = str(workspace)
    doc.STATE_DIR = str(state)
    doc.STATE_FILE = str(state / "doc_gate.json")
    doc.PRECISION_GATE_FILE = str(state / "precision_gate.json")
    hook.PROJECT_ROOT = str(workspace)
    hook._PRECISION_GATE_STATE = doc.PRECISION_GATE_FILE
    doc.is_kernel_file = lambda path: path.endswith(doc.KERNEL_EXTENSIONS) and any(
        segment in "/" + path.replace("\\", "/").lstrip("/") for segment in doc.KERNEL_SEGMENTS
    )
    # The upstream doc CLI logs INFO without configuring a handler. Capture its
    # structured events directly instead of interpreting absent stdout as allow.
    return doc, hook


def within(path, root):
    return path == root or root in path.parents


def event_gate(workspace, mode, event, doc):
    tool = event.get("tool_name")
    data = event.get("tool_input")
    expected = {"pre": ("Edit", "Write"), "post": ("Read",), "skill-post": ("Skill",)}
    if tool not in expected[mode] or not isinstance(data, dict):
        raise ValueError("Unexpected event type for mode; refusing an implicit allow")
    data = dict(data)
    if mode in ("pre", "post"):
        if not data.get("file_path"):
            raise ValueError("file_path is required")
        logical = Path(data["file_path"])
        logical = Path(os.path.abspath(workspace / logical if not logical.is_absolute() else logical))
        path = logical.resolve()
        if mode == "pre" and not within(path, workspace):
            raise ValueError("Edit target escapes the dedicated workspace")
        if mode == "post" and not path.is_file():
            raise ValueError("Read evidence must refer to an existing file")
        data["file_path"] = (logical if mode == "post" else path).as_posix()
    else:
        skill = data.get("skill")
        if skill == "tilelang2ascend-precision-tuning":
            data["skill"] = "ascendc-precision-tuning"
        elif skill != "ascendc-precision-debug":
            raise ValueError("Only completed precision-debug/tuning work can unlock edits")
        state = doc.read_precision_state()
        debug = state.get("debug_call_count", 0)
        tune = state.get("tune_call_count", 0)
        if debug + tune >= 12 or (data["skill"] == "ascendc-precision-debug" and debug >= 7):
            raise ValueError("Precision retry budget exhausted for this stage")
        if data["skill"] == "ascendc-precision-tuning" and (debug < 7 or tune >= 5):
            raise ValueError("D2 requires completed D1 budget and has at most five attempts")
    results = []
    doc.emit = results.append
    {"pre": doc.handle_pre, "post": doc.handle_post, "skill-post": doc.handle_skill_post}[mode](tool, data)
    if len(results) != 1:
        raise ValueError("Upstream gate did not emit exactly one decision")
    if mode == "pre" and results[0]["hookSpecificOutput"].get("permissionDecision") == "allow":
        state = doc.read_precision_state()
        state["last_classification"] = "STALE"
        state["invalidated_by"] = data["file_path"]
        doc.write_precision_state(state)
    return results[0]


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validator_dependencies(workspace, hook, script):
    """Bind the task-local verifier actually launched by the original shell."""
    if script.name != "evaluate_ascendc.sh":
        return {}
    relative = "tilelang2ascend-translator/scripts/verification_ascendc.py"
    expected = hook._workflow_plugin / "skills" / relative
    actual = (workspace / ".claude/skills" / relative).resolve()
    if ((not within(actual, workspace) and actual != expected.resolve())
            or not actual.is_file() or sha256(actual) != sha256(expected)):
        raise ValueError("Shell verifier must match the specified CANNBot verification_ascendc.py")
    return {str(actual): sha256(actual)}


INPUT_SUFFIXES = {".json", ".jsonl", ".csv", ".tsv", ".npy", ".npz", ".pt", ".pth", ".bin", ".pkl"}
SOURCE_SUFFIXES = {".py", ".cpp", ".h", ".hpp", ".cc", ".c", ".cxx", ".asc", ".cmake", ".sh"}
EXCLUDED_DIRS = {".cannbot", ".claude", ".git", "__pycache__", "build", "dist", "perf_tuning", "profiling", "workflows"}


def fingerprints(target):
    result = {"source": {}, "reference": {}, "inputs": {}}
    for path in sorted(target.rglob("*")):
        relative = path.relative_to(target)
        if any(part in EXCLUDED_DIRS for part in relative.parts) or path.name == "performance.json" or not path.is_file():
            continue
        if not within(path.resolve(), target):
            raise ValueError("Candidate/reference/input files must remain in the task directory")
        if path.name == "model.py":
            kind = "reference"
        elif path.suffix in INPUT_SUFFIXES:
            kind = "inputs"
        elif path.suffix in SOURCE_SUFFIXES or path.name == "CMakeLists.txt":
            kind = "source"
        else:
            continue
        result[kind][relative.as_posix()] = sha256(path)
    return result


def actual_cases(stdout, stderr):
    # Both original single-task verifiers emit one comparison line per case.
    indices = [int(x) for x in re.findall(r"(?m)^case\[(\d+)\]:", stdout + "\n" + stderr)]
    return len(indices) if indices and indices == list(range(len(indices))) else None


def coverage_evidence(target, snapshot, count, expected_cases=None, full_manifest=None):
    evidence = {"actual_cases": count, "expected_cases": expected_cases, "scope": "unknown", "full": False}
    if expected_cases is not None and (expected_cases < 1 or count != expected_cases):
        evidence["error"] = "Actual case count does not match expected_cases"
    if full_manifest is not None:
        manifest = json.loads(full_manifest.read_text(encoding="utf-8"))
        expected = manifest.get("expected_cases")
        files = manifest.get("files")
        required = {**snapshot["reference"], **snapshot["inputs"]}
        if manifest.get("scope") != "full" or type(expected) is not int or expected < 1:
            raise ValueError("Full manifest requires scope=full and positive integer expected_cases")
        if not isinstance(files, dict) or "model.py" not in files or not set(required).issubset(files):
            raise ValueError("Full manifest must cover model.py and every discovered input file")
        for relative, digest in files.items():
            path = (target / relative).resolve()
            if not within(path, target) or not path.is_file() or sha256(path) != digest:
                raise ValueError("Full manifest file/hash mismatch: " + relative)
        if expected_cases is not None and expected_cases != expected:
            raise ValueError("Full manifest expected_cases conflicts with explicit expected_cases")
        evidence.update(expected_cases=expected, manifest=str(full_manifest.resolve()), manifest_sha256=sha256(full_manifest))
        if count != expected:
            evidence["error"] = "Actual case count does not match frozen full manifest"
        elif "error" not in evidence:
            evidence.update(scope="full", full=True)
    return evidence


def check_validation(workspace, hook, require_full=False):
    state = hook._read_precision_gate()
    if state.get("d_class_active") or state.get("last_classification") != "PASS":
        return {"passed": False, "reason": "Latest AscendC precision state is not PASS"}
    record_path = Path(state.get("last_run", "")).resolve()
    if not within(record_path, workspace) or not record_path.is_file():
        raise ValueError("Missing or escaping validation record")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if record.get("kind") != "ascendc" or record.get("classification") != "PASS" or record.get("returncode") != 0:
        return {"passed": False, "reason": "Record is not a successful AscendC precision run"}
    if record.get("cannbot_source") != hook._workflow_source:
        return {"passed": False, "reason": "CANNBot gate source identity changed or is missing"}
    validator = Path(record["argv"][1]).resolve()
    skill, _ = SCRIPTS.get(validator.name, (None, None))
    if (not skill or validator != (hook._workflow_plugin / "skills" / skill / "scripts" / validator.name).resolve()
            or not validator.is_file() or sha256(validator) != record.get("validator_sha256")):
        return {"passed": False, "reason": "Validation script identity changed"}
    try:
        if validator_dependencies(workspace, hook, validator) != record.get("validator_dependencies", {}):
            return {"passed": False, "reason": "Indirect validation script identity changed"}
    except (ValueError, OSError) as exc:
        return {"passed": False, "reason": str(exc)}
    target = Path(record["target"]).resolve()
    if not within(target, workspace):
        raise ValueError("Recorded task escapes workspace")
    if fingerprints(target) != record.get("fingerprints"):
        return {"passed": False, "reason": "Candidate/reference/input fingerprints changed"}
    if "model.py" not in record["fingerprints"]["reference"] or "model_new_ascendc.py" not in record["fingerprints"]["source"]:
        return {"passed": False, "reason": "Reference/candidate identity is incomplete"}
    for name in ("stdout", "stderr"):
        path = Path(record[name]).resolve()
        if not within(path, workspace) or not path.is_file() or sha256(path) != record.get(name + "_sha256"):
            return {"passed": False, "reason": "Raw validation log is missing or changed"}
    coverage = record.get("coverage", {})
    if not coverage.get("actual_cases") or coverage.get("error"):
        return {"passed": False, "reason": "Actual validation coverage is unknown or mismatched"}
    if coverage.get("manifest"):
        manifest = Path(coverage["manifest"])
        if not manifest.is_file() or sha256(manifest) != coverage["manifest_sha256"]:
            return {"passed": False, "reason": "Frozen full-case manifest changed"}
        try:
            current_coverage = coverage_evidence(target, record["fingerprints"], coverage["actual_cases"], coverage["expected_cases"], manifest)
        except (ValueError, OSError) as exc:
            return {"passed": False, "reason": str(exc)}
        if not current_coverage.get("full"):
            return {"passed": False, "reason": "Frozen input manifest no longer matches"}
    if require_full:
        if not coverage.get("full"):
            return {"passed": False, "reason": "Full-case evidence is unavailable"}
    return {"passed": True, "coverage": coverage, "record": str(record_path), "fingerprints_match": True}


def classify(kind, returncode, stdout, stderr, hook):
    if kind == "ast":
        return "AST_PASS" if returncode == 0 else "AST_FAIL"
    combined = stdout + "\n" + stderr
    # Only the standalone verification report result is accepted. Logging may
    # prefix the first line; arbitrary prose containing PASS is not a result.
    cleaned = re.sub(r"(?m)^(?:INFO|ERROR|WARNING):\s*", "", combined)
    results = re.findall(r"(?im)^\s*Result:\s*(pass|fail)\s*$", cleaned)
    errors = hook._A_CLASS_PATTERN_RE.search(cleaned)
    if returncode == 0 and results and all(x.lower() == "pass" for x in results) and not errors:
        return "PASS"
    if errors:
        return "A"
    if results and results[-1].lower() == "fail" and hook._D_CLASS_NUMERIC_RE.search(cleaned):
        return "D"
    return "A" if returncode != 0 else "UNKNOWN"


def persist_result(hook, classification, stdout, target, record):
    previous = hook._read_precision_gate()
    # Preserve D1/D2 counters across intermittent compiler/runtime failures.
    # UNKNOWN and A never clear an outstanding precision failure.
    if classification in ("PASS", "D"):
        hook._update_precision_gate(classification, stdout, str(target))
        state = hook._read_precision_gate()
        if classification == "PASS":
            for key in ("debug_call_count", "tune_call_count", "stage"):
                if key in previous:
                    state[key] = previous[key]
    else:
        state = previous or {"d_class_active": False, "edits_allowed": 0}
        state["edits_allowed"] = 0
    state["last_classification"] = classification
    state["last_run"] = str(record)
    Path(hook._PRECISION_GATE_STATE).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def run_validation(workspace, argv, hook, expected_cases=None, full_manifest=None):
    if argv and argv[0] == "--":
        argv = argv[1:]
    if len(argv) < 3:
        raise ValueError("Expected interpreter, known validation script, and task/model path")
    script = Path(argv[1])
    script = (workspace / script).resolve() if not script.is_absolute() else script.resolve()
    if script.name not in SCRIPTS:
        raise ValueError("Unsupported script; remote evaluate_tilelang.sh is intentionally excluded")
    skill, kind = SCRIPTS[script.name]
    expected = (hook._workflow_plugin / "skills" / skill / "scripts" / script.name).resolve()
    if script != expected or not script.is_file():
        raise ValueError("Validation script must resolve to the specified CANNBot checkout")
    validator_sha = sha256(script)
    dependencies = validator_dependencies(workspace, hook, script)
    interpreter = Path(argv[0]).name.lower()
    if kind != "ast" and not os.environ.get("ASCEND_RT_VISIBLE_DEVICES"):
        raise ValueError("Set the verified ASCEND_RT_VISIBLE_DEVICES explicitly")
    if script.suffix == ".sh":
        if interpreter not in ("bash", "bash.exe"):
            raise ValueError("Shell validation requires bash")
        if not os.environ.get("ASCENDC_SOC_VERSION") or not os.environ.get("ASCEND_RT_VISIBLE_DEVICES"):
            raise ValueError("Set verified ASCENDC_SOC_VERSION and ASCEND_RT_VISIBLE_DEVICES explicitly")
    elif not re.fullmatch(r"python(?:3(?:\.\d+)?)?(?:\.exe)?", interpreter):
        raise ValueError("Python validation requires a Python interpreter")
    target = Path(argv[2])
    target = (workspace / target).resolve() if not target.is_absolute() else target.resolve()
    if not within(target, workspace) or not target.exists():
        raise ValueError("Validation target must exist within the dedicated workspace")
    if argv[3:] and not (script.name in ("verification_ascendc.py", "evaluate_ascendc.sh") and argv[3:] == ["--non-compute"]):
        raise ValueError("Only single-task validation and optional --non-compute are supported")
    run_dir = workspace / ".cannbot/gate-runs" / uuid.uuid4().hex
    if not within(run_dir.resolve(), workspace):
        raise ValueError("Validation log directory escapes workspace")
    run_dir.mkdir(parents=True)
    snapshot = fingerprints(target) if kind != "ast" else None
    out_path, err_path = run_dir / "stdout.log", run_dir / "stderr.log"
    env = dict(os.environ, WORKDIR=str(workspace), PROJECT_ROOT=str(workspace))
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUTF8"] = "1"
    profiling = hook._workflow_plugin.parents[1] / "ops/ops-profiling/scripts"
    env["PYTHONPATH"] = os.pathsep.join((str(workspace), str(profiling), env.get("PYTHONPATH", "")))
    command = [argv[0], str(script), str(target), *argv[3:]]
    if kind == "ascendc":
        persist_result(hook, "RUNNING", "", target, run_dir / "result.json")
    try:
        with out_path.open("wb") as stdout, err_path.open("wb") as stderr:
            result = subprocess.run(command, cwd=workspace, env=env, stdout=stdout, stderr=stderr, timeout=1800)
        returncode = result.returncode
    except subprocess.TimeoutExpired:
        returncode = 124
        with err_path.open("ab") as stderr:
            stderr.write(b"\n[Codex gate] timeout after 1800 seconds\n")
    except OSError as exc:
        returncode = 127
        err_path.write_text(str(exc), encoding="utf-8")
    stdout = out_path.read_text(encoding="utf-8", errors="replace")
    stderr = err_path.read_text(encoding="utf-8", errors="replace")
    classification = classify(kind, returncode, stdout, stderr, hook)
    try:
        coverage = coverage_evidence(target, snapshot, actual_cases(stdout, stderr), expected_cases, full_manifest) if kind != "ast" else None
    except (ValueError, OSError) as exc:
        coverage = {"actual_cases": actual_cases(stdout, stderr), "scope": "unknown", "full": False, "error": str(exc)}
    if kind != "ast" and (snapshot != fingerprints(target) or coverage.get("error")):
        classification = "UNKNOWN"
    try:
        if sha256(script) != validator_sha or validator_dependencies(workspace, hook, script) != dependencies:
            classification = "UNKNOWN"
    except (ValueError, OSError):
        classification = "UNKNOWN"
    record_path = run_dir / "result.json"
    record = {"argv": command, "kind": kind, "returncode": returncode,
              "classification": classification, "passed": classification in ("PASS", "AST_PASS"),
              "stdout": str(out_path), "stderr": str(err_path), "record": str(record_path),
              "stdout_sha256": sha256(out_path), "stderr_sha256": sha256(err_path),
              "target": str(target), "fingerprints": snapshot, "coverage": coverage,
              "cannbot_source": hook._workflow_source, "validator_sha256": validator_sha,
              "validator_dependencies": dependencies}
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    if kind == "ascendc":
        persist_result(hook, classification, stdout, target, record_path)
    return record


def main():
    # JSON CLI uses UTF-8 consistently, including Windows redirected pipes.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    action = argv[0] if argv and argv[0] in ("run", "check") else "event"
    if action != "event":
        argv.pop(0)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--cannbot-root", type=Path, help="Read-only external checkout; or CANNBOT_SOURCE_ROOT")
    if action == "run":
        parser.add_argument("--expected-cases", type=int)
        parser.add_argument("--full-manifest", type=Path)
        parser.add_argument("command", nargs=argparse.REMAINDER)
    elif action == "check":
        parser.add_argument("--require-full", action="store_true")
    else:
        parser.add_argument("--mode", required=True, choices=("pre", "post", "skill-post"))
    args = parser.parse_args(argv)
    try:
        workspace = args.workspace.resolve()
        if not workspace.is_dir():
            raise ValueError("Dedicated workspace must already exist")
        doc, hook = modules(workspace, args.cannbot_root)
        if action == "run":
            result = run_validation(workspace, args.command, hook, args.expected_cases, args.full_manifest)
            status = 0 if result["passed"] else 1
        elif action == "check":
            result = check_validation(workspace, hook, args.require_full)
            status = 0 if result["passed"] else 1
        else:
            event = json.load(sys.stdin)
            if not isinstance(event, dict):
                raise ValueError("Event must be a JSON object")
            result = event_gate(workspace, args.mode, event, doc)
            status = 0 if result["hookSpecificOutput"].get("permissionDecision") == "allow" else 1
    except Exception as exc:
        result = {"passed": False, "error": f"{type(exc).__name__}: {exc}"}
        status = 2
    print(json.dumps(result, ensure_ascii=False))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
