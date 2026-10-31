"""Persist a Codex round reservation; only the coordinator may invoke this.

Uses the Codex validation adapter over the unchanged native schema.
The selections file is the JSON stdout of wm_ops.py select. No NPU execution.
"""
import argparse
import json
import os
from pathlib import Path

from world_model_adapter import load_native, validate


def reserve(wm_path, selections_path, map_path, wm_scripts, score_base="native"):
    wm_path, map_path = Path(wm_path).resolve(), Path(map_path).resolve()
    root = wm_path.parent
    if not map_path.is_relative_to(root):
        raise ValueError("parallel map must stay inside this run")
    if map_path.exists():
        raise ValueError("round already reserved; inspect state and resume existing mapping")
    native = load_native(wm_scripts)
    wm = json.loads(wm_path.read_text(encoding="utf-8"))
    selections = json.loads(Path(selections_path).read_text(encoding="utf-8-sig"))
    errors = validate(wm, native, score_base)["errors"]
    if errors:
        raise ValueError("invalid world model: " + "; ".join(errors))
    if not isinstance(selections, list) or not selections:
        raise ValueError("selection must be a nonempty JSON array")
    nodes = wm["decision_tree"]["nodes"]
    mapping, seen = {}, set()
    for selection in selections:
        idx, nid = selection["parallel_index"], selection["node_id"]
        if not isinstance(idx, int) or isinstance(idx, bool) or idx < 0:
            raise ValueError("parallel_index must be a nonnegative integer")
        if str(idx) in mapping or nid in seen:
            raise ValueError("duplicate lane or node")
        if nid not in nodes or nodes[nid]["status"] != "open":
            raise ValueError(f"node {nid} is missing or not open")
        mapping[str(idx)] = nid
        seen.add(nid)
    for nid in seen:
        nodes[nid]["status"] = "in_progress"
    errors = validate(wm, native, score_base)["errors"]
    if errors:
        raise ValueError("invalid reserved model: " + "; ".join(errors))
    map_path.parent.mkdir(parents=True, exist_ok=True)
    # Write the recovery record first. A crash between writes leaves a visible
    # reservation that must be reconciled, never silently dispatched twice.
    with map_path.open("x", encoding="utf-8") as stream:
        json.dump(mapping, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary = wm_path.with_name(wm_path.name + ".reservation.tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(wm, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, wm_path)
    return mapping


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wm-path", required=True)
    parser.add_argument("--selections", required=True)
    parser.add_argument("--parallel-map", required=True)
    parser.add_argument("--wm-scripts", required=True)
    parser.add_argument("--score-base", choices=("native", "pytorch"), default="native")
    args = parser.parse_args()
    try:
        print(json.dumps(reserve(args.wm_path, args.selections,
                                 args.parallel_map, args.wm_scripts, args.score_base)))
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(2, f"reservation rejected: {exc}\n")
