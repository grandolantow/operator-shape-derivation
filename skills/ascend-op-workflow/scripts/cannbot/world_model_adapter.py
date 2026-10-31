"""Validate Codex world models without editing or rescaling CANNBot data.

The explicit pytorch score base admits finite positive speedups below one.
All other native validation errors remain fatal. This is a control-flow check,
not evidence of kernel correctness or measured performance.
"""

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys


def load_native(wm_scripts):
    """Load the specified native version read-only, including sibling imports."""
    path = Path(wm_scripts).resolve() / "wm_ops.py"
    name = "_cannbot_wm_" + hashlib.sha256(str(path).encode()).hexdigest()[:16]
    if name not in sys.modules:
        # Imports must not create __pycache__ in a read-only native checkout.
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(path.parent))
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            del sys.modules[name]
            raise
    return sys.modules[name]


def validate(wm, native, score_base="native"):
    """Return adapter errors and the unaltered native verdict separately."""
    if score_base not in {"native", "pytorch"}:
        raise ValueError("score base must be native or pytorch")
    best = wm.get("best_score")
    positive = (isinstance(best, (int, float)) and not isinstance(best, bool)
                and math.isfinite(best) and best > 0)
    if not positive:
        return {"valid": False, "score_base": score_base, "native_errors": None,
                "errors": ["best_score must be a finite positive number"],
                "compatibility": None}
    native_errors = native.validate(wm)
    errors = list(native_errors)
    compatibility = None
    if score_base == "pytorch" and best < 1:
        # Match only the known native score-floor error, never an entire class
        # of errors or the whole validation result. Unknown versions fail closed.
        floor_error = f"Invariant 2 FAIL: best_score={best} is less than 1.0"
        if errors.count(floor_error) == 1:
            errors.remove(floor_error)
            compatibility = "positive_pytorch_speedup_below_one"
    return {"valid": not errors, "score_base": score_base,
            "native_errors": native_errors, "errors": errors,
            "compatibility": compatibility}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wm-scripts", required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--score-base", choices=("native", "pytorch"), default="native")
    args = parser.parse_args()
    try:
        wm = json.loads(Path(args.path).read_text(encoding="utf-8-sig"))
        report = validate(wm, load_native(args.wm_scripts), args.score_base)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(2, f"world model rejected: {exc}\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
