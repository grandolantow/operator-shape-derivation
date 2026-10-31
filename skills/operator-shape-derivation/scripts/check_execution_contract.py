"""Validate execution-contract structure and dependency propagation, not rule semantics."""
import argparse
import json
from pathlib import Path

KNOWN = {"configured", "observed", "derived", "assumed"}
UNRESOLVED = {"unknown", "conditional"}
VAGUE_SCOPES = {"unknown", "ambiguous", "unspecified", "tbd", "未确定", "未知", "不明确"}


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def validate_contract(data):
    """Return a JSON-compatible report. Exit codes: 0 ready, 2 blocked, 1 invalid."""
    issues = []

    def issue(code, message, quantity=None, invalid=True):
        item = {"code": code, "message": message, "invalid": invalid}
        if quantity is not None:
            item["quantity"] = quantity
        issues.append(item)

    contract = data.get("execution_contract") if isinstance(data, dict) else None
    if not isinstance(contract, dict):
        return {"exit_code": 1, "rule_semantics_verified": False,
                "issues": [{"code": "invalid-contract", "message": "execution_contract must be an object", "invalid": True}],
                "quantities": {}, "export_ready": False}
    quantities = contract.get("quantities")
    required = contract.get("required_for_export")
    decisions = contract.get("decisions", [])
    if not isinstance(quantities, dict):
        issue("invalid-quantities", "quantities must be an object")
        quantities = {}
    if not isinstance(required, list) or not all(_text(x) for x in required):
        issue("invalid-required", "required_for_export must be a list of quantity IDs")
        required = []
    if not isinstance(decisions, list):
        issue("invalid-decisions", "decisions must be a list")
        decisions = []
    dependencies = {}
    assumptions = {}
    for key, q in quantities.items():
        if not _text(key) or not isinstance(q, dict):
            issue("invalid-quantity", "quantity needs a nonempty ID and object", key)
            q = {}
        status = q.get("status") if isinstance(q.get("status"), str) else None
        if not isinstance(status, str) or status not in KNOWN | UNRESOLVED:
            issue("invalid-status", "unsupported quantity status", key)
        scope = q.get("scope")
        if not _text(scope) or (status in KNOWN and scope.strip().lower() in VAGUE_SCOPES):
            issue("invalid-scope", "known quantities require a concrete nonempty scope", key)
        if not _text(q.get("evidence")):
            issue("missing-evidence", "quantity requires source evidence", key)
        if "value" not in q or (status in KNOWN and q.get("value") is None):
            issue("missing-value", "known quantities require a nonnull value; all quantities require a value field", key)
        if status in UNRESOLVED and q.get("value") is not None:
            issue("unresolved-value", "unknown/conditional values must be null", key)
        deps = q.get("depends_on", [])
        if not isinstance(deps, list) or not all(_text(x) for x in deps):
            issue("invalid-dependencies", "depends_on must list quantity IDs", key)
            deps = []
        dependencies[key] = deps
        for dep in deps:
            if dep not in quantities:
                issue("missing-dependency", f"dependency {dep!r} does not exist", key)
        if status == "derived" and not deps and not _text(q.get("rule_evidence")):
            issue("missing-derivation", "derived quantity needs depends_on or rule_evidence", key)
        notes = q.get("assumptions", [])
        if not isinstance(notes, list) or not all(_text(x) for x in notes):
            issue("invalid-assumptions", "assumptions must contain nonempty descriptions and authorization sources", key)
            notes = []
        if status == "assumed" and not notes:
            issue("missing-assumption", "assumed quantity needs explicit assumptions", key)
        assumptions[key] = notes
    for key in required:
        if key not in quantities:
            issue("missing-required", f"required quantity {key!r} does not exist")

    pending = {}
    decision_ids = set()
    for decision in decisions:
        if not isinstance(decision, dict):
            issue("invalid-decision", "decision must be an object")
            continue
        did = decision.get("id")
        if not _text(did) or did in decision_ids:
            issue("invalid-decision-id", "decision ID must be nonempty and unique")
        else:
            decision_ids.add(did)
        affected = decision.get("quantities")
        if not isinstance(affected, list) or not affected or not all(_text(x) for x in affected):
            issue("invalid-decision-quantities", "decision requires affected quantity IDs")
            affected = []
        for key in affected:
            if key not in quantities:
                issue("missing-decision-quantity", f"decision quantity {key!r} does not exist")
        if not _text(decision.get("reason")) or not _text(decision.get("question")):
            issue("invalid-decision-context", "decision needs reason and question")
        if decision.get("status") not in ("pending", "resolved"):
            issue("invalid-decision-status", "decision status must be pending or resolved")
        elif decision["status"] == "resolved" and not _text(decision.get("evidence")):
            issue("missing-resolution", "resolved decision needs evidence")
        elif decision["status"] == "pending" and _text(did):
            pending[did] = set(affected)

    closures = {}
    def closure(key, active):
        if key in active:
            issue("dependency-cycle", "dependency cycle: " + " -> ".join(active + [key]), key)
            return {key}
        if key in closures:
            return closures[key]
        result = {key}
        for dep in dependencies.get(key, []):
            result.update(closure(dep, active + [key]))
        closures[key] = result
        return result

    reports = {}
    for key, q in quantities.items():
        chain = closure(key, [])
        unknown = sorted(x for x in chain if isinstance(quantities.get(x), dict)
                         and isinstance(quantities[x].get("status"), str) and quantities[x].get("status") in UNRESOLVED)
        waiting = sorted(did for did, affected in pending.items() if chain & affected)
        inherited = [{"quantity": x, "description": note}
                     for x in sorted(chain) for note in assumptions.get(x, [])]
        if isinstance(q, dict) and isinstance(q.get("status"), str) and q.get("status") in KNOWN and unknown:
            issue("known-depends-on-unresolved", "declared known quantity depends on unresolved quantities", key)
        if isinstance(q, dict) and q.get("status") == "observed" and inherited:
            issue("observed-depends-on-assumption", "assumption-dependent derivation cannot be labeled observed", key)
        reports[key] = {"declared_status": q.get("status") if isinstance(q, dict) else None,
                        "dependencies_transitive": sorted(chain - {key}),
                        "unresolved_quantities": unknown, "pending_decisions": waiting,
                        "assumptions": inherited}
    needed = set().union(*(closures.get(key, {key}) for key in required)) if required else set()
    for key in sorted(needed):
        q = quantities.get(key)
        if isinstance(q, dict) and isinstance(q.get("status"), str) and q.get("status") in UNRESOLVED:
            if not any(affected & closures.get(key, {key}) for affected in pending.values()):
                issue("missing-decision", "export dependency is unresolved and needs a pending decision with question and reason", key, False)
    invalid_quantities = {item.get("quantity") for item in issues if item["invalid"]}
    for key, report in reports.items():
        report["available"] = not (report["unresolved_quantities"] or report["pending_decisions"]
                                  or closures[key] & invalid_quantities)
    invalid = any(item["invalid"] for item in issues)
    ready = not invalid and all(reports.get(key, {}).get("available", False) for key in required)
    return {"exit_code": 1 if invalid else (0 if ready else 2),
            "rule_semantics_verified": False, "export_ready": ready,
            "required_for_export": required, "quantities": reports, "issues": issues}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = validate_contract(json.loads(args.input.read_text(encoding="utf-8-sig")))
    except (OSError, ValueError) as exc:
        report = {"exit_code": 1, "export_ready": False, "rule_semantics_verified": False,
                  "issues": [{"code": "input-error", "message": str(exc), "invalid": True}]}
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
