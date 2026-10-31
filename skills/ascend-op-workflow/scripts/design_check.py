"""Read-only structural gate for pre-implementation design review, not acceptance."""

import argparse
import hashlib
import json
import sys
from pathlib import Path


COSTS = (
    "reduction_calls", "scalar_ub_accesses", "synchronization", "dma_calls",
    "dma_granularity", "padding_and_tails", "repeated_input_reads",
)


class DesignError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise DesignError(message)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def fields(value, names, label):
    require(isinstance(value, dict), f"{label} must be an object")
    for name in names:
        require(text(value.get(name)), f"{label}.{name} needs a nonempty explanation")


def items(value, label, nonempty=True):
    require(isinstance(value, list) and (bool(value) or not nonempty),
            f"{label} must be {'a nonempty' if nonempty else 'an'} array")
    return value


def assessment_digest(record):
    require(isinstance(record, dict), "Record must be an object")
    payload = {k: v for k, v in record.items() if k != "review"}
    data = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def check(record, root):
    require(isinstance(record, dict), "Record must be an object")
    require(record.get("schema") == "generation-design-review-v1", "Unsupported schema")
    fields(record, ("author", "reviewer", "coverage_basis", "route_selection_reason"), "record")
    require(record["author"].strip() != record["reviewer"].strip(),
            "Author and independent reviewer must be distinct declared actors")
    artifacts = record.get("artifacts")
    require(isinstance(artifacts, dict) and
            {"design", "contract", "workload", "environment"} <= artifacts.keys(),
            "Bind design, contract, workload/manifest and environment artifacts")
    for name, ref in artifacts.items():
        fields(ref, ("path", "sha256"), f"artifacts.{name}")
        path = (root / ref["path"]).resolve(strict=True)
        require(path.is_file(), f"Artifact {name} is not a file")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        require(actual == ref["sha256"], f"Artifact {name} hash mismatch")

    contractions = record.get("matrix_contractions")
    fields(contractions, ("reason",), "matrix_contractions")
    require(type(contractions.get("applicable")) is bool, "Declare matrix applicability")
    operations = items(contractions.get("operations"), "matrix operations",
                       contractions["applicable"])
    require(all(text(x) for x in operations), "Matrix operation names must be nonempty")
    require(contractions["applicable"] or not operations,
            "Non-matrix assessment cannot list matrix operations")
    options = {}
    for option in items(record.get("route_options"), "route_options"):
        fields(option, ("primitive", "support_domain", "precision", "workspace_and_adaptation",
                        "selection_reason"), "route option")
        require(option.get("support_status") in {"verified", "unknown", "unsupported"},
                "Route support status must be verified/unknown/unsupported")
        evidence = items(option.get("evidence"), "route evidence")
        require(all(text(x) for x in evidence), "Route evidence needs concrete source references")
        require(option["primitive"] not in options, "Route primitive names must be unique")
        options[option["primitive"]] = option

    group_ids = set()
    selected = set()
    for group in items(record.get("geometry_groups"), "geometry_groups"):
        fields(group, ("id", "geometry", "selected_route", "cost_basis"), "geometry group")
        require(group["id"] not in group_ids, "Duplicate geometry group ID")
        group_ids.add(group["id"])
        route = group["selected_route"]
        require(route in options, "Selected route must reference a declared route primitive")
        require(options[route]["support_status"] != "unsupported",
                f"Selected route {route} is unsupported; revise design")
        selected.add(route)
        costs = group.get("costs")
        require(isinstance(costs, dict) and set(COSTS) <= costs.keys(),
                f"Each group needs cost dimensions: {', '.join(COSTS)}")
        for name in COSTS:
            cost = costs[name]
            fields(cost, ("scope", "basis"), f"cost.{name}")
            require(cost.get("status") in {"estimated", "unknown", "not_applicable"},
                    f"Invalid cost status for {name}")
            if cost["status"] == "estimated":
                value = cost.get("estimate")
                require(text(value) or (type(value) in (int, float) and value >= 0),
                        f"Estimated cost {name} needs a nonnegative count or formula")

    findings = {}
    for finding in items(record.get("findings"), "findings", False):
        fields(finding, ("id", "observation"), "finding")
        require(finding["id"] not in findings, "Duplicate finding ID")
        findings[finding["id"]] = finding
    for route in selected:
        option = options[route]
        if option["support_status"] == "unknown":
            identifier = option.get("support_finding_id")
            require(text(identifier) and identifier in findings,
                    f"Unknown selected route {route} needs a support_finding_id and risk response")
    review = record.get("review")
    fields(review, ("rationale", "assessment_sha256"), "review")
    require(review["assessment_sha256"] == assessment_digest(record),
            "Assessment changed or was not independently reviewed; refresh review fingerprint")
    require(review.get("correctness_feasibility") in {"feasible", "unknown", "blocked"},
            "Invalid correctness feasibility")
    require(review.get("performance_feasibility") in {"feasible", "high_risk", "unknown"},
            "Invalid performance feasibility")
    require(review.get("decision") in {"proceed", "revise"}, "Invalid implementation decision")
    reviewed = {}
    for disposition in items(review.get("findings"), "review.findings", False):
        fields(disposition, ("id", "reviewer_rationale"), "review finding")
        identifier = disposition["id"]
        require(identifier in findings and identifier not in reviewed,
                "Review finding IDs must match author findings exactly once")
        status = disposition.get("status")
        require(status in {"open", "resolved", "accepted_risk"}, "Invalid finding disposition")
        if status != "open":
            fields(findings[identifier], ("author_response", "validation_plan"), "closed finding")
        reviewed[identifier] = status
    require(reviewed.keys() == findings.keys(), "Every finding needs independent disposition")
    if (review["performance_feasibility"] != "feasible" or
            review["correctness_feasibility"] != "feasible"):
        require(bool(findings), "Unknown/high-risk feasibility needs explicit findings")
    ready = (review["decision"] == "proceed" and
             review["correctness_feasibility"] != "blocked" and
             all(status != "open" for status in reviewed.values()))
    return {"status": "IMPLEMENTATION_READY" if ready else "DESIGN_REVISION_REQUIRED",
            "implementation_ready": ready,
            "correctness_feasibility": review["correctness_feasibility"],
            "performance_feasibility": review["performance_feasibility"],
            "assessment_sha256": assessment_digest(record),
            "measured_correctness": None, "measured_performance": None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", required=True, type=Path)
    parser.add_argument("--assessment-digest", action="store_true",
                        help="Fingerprint author payload only; does not pass the gate")
    args = parser.parse_args(argv)
    try:
        # Reject non-standard NaN/Infinity rather than hashing or accepting them as counts.
        def invalid_constant(value):
            raise DesignError(f"Invalid JSON numeric constant: {value}")

        record_bytes = args.record.read_bytes()
        record = json.loads(record_bytes.decode("utf-8-sig"), parse_constant=invalid_constant)
        if args.assessment_digest:
            output = {"status": "FINGERPRINT_ONLY", "implementation_ready": False,
                      "assessment_sha256": assessment_digest(record)}
        else:
            output = check(record, args.record.resolve().parent)
        output["record_sha256"] = hashlib.sha256(record_bytes).hexdigest()
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0 if args.assessment_digest or output["implementation_ready"] else 2
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"status": "INVALID_DESIGN_REVIEW", "implementation_ready": False,
                          "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
