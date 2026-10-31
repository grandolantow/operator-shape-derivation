"""Design gate invariants; no compiler, external process or NPU required."""

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import design_check


class DesignCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        template = Path(__file__).resolve().parents[1] / "references/generation-design-review.template.json"
        self.template = json.loads(template.read_text(encoding="utf-8"))
        self.record = json.loads(json.dumps(self.template))
        for name in self.record["artifacts"]:
            path = self.root / f"{name}.txt"
            path.write_text(f"Fixture {name}: one small vector domain", encoding="utf-8")
            self.record["artifacts"][name] = {
                "path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        self.record.update(author="architect-1", reviewer="reviewer-2",
                           coverage_basis="Entire fixture workload is one small vector shape",
                           route_selection_reason="No matrix contraction; vector addition")
        self.record["matrix_contractions"] = {
            "applicable": False, "reason": "Elementwise addition", "operations": [],
        }
        self.record["route_options"] = [{
            "primitive": "Vector Add", "support_domain": "FP32 contiguous fixture domain",
            "precision": "FP32 input/output", "workspace_and_adaptation": "No GM workspace",
            "support_status": "verified", "evidence": ["Fixture SDK Add declaration"],
            "selection_reason": "Direct elementwise operation",
        }]
        group = self.record["geometry_groups"][0]
        group.update(id="small", geometry="one small contiguous vector",
                     selected_route="Vector Add", cost_basis="Formula per task; fixture only")
        for cost in group["costs"].values():
            cost.update(status="estimated", scope="per_task", estimate="ceil(N/tile), calls",
                        basis="One call per logical tile; padding handled separately")
        self.record["findings"] = []
        self.record["review"].update(correctness_feasibility="feasible",
                                     performance_feasibility="feasible", decision="proceed",
                                     rationale="Reviewed fixture domain and bound artifacts", findings=[])
        self.sign()

    def sign(self):
        self.record["review"]["assessment_sha256"] = design_check.assessment_digest(self.record)

    def invoke(self, record=None, *args):
        path = self.root / "review.json"
        path.write_text(json.dumps(self.record if record is None else record), encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = design_check.main(["--record", str(path), *args])
        return code, json.loads(out.getvalue() or err.getvalue())

    def add_risk(self, status="accepted_risk"):
        self.record["findings"] = [{
            "id": "opaque", "observation": "Library internal DMA count unknown",
            "author_response": "Use supported primitive; keep unknown counts explicit",
            "validation_plan": "After first-correct freeze, inspect fixed10 profile",
        }]
        self.record["review"].update(performance_feasibility="unknown", findings=[{
            "id": "opaque", "status": status,
            "reviewer_rationale": "Reviewed supported route and explicit post-freeze plan",
        }])
        self.sign()

    def test_non_matrix_single_geometry_can_proceed_without_measured_claims(self):
        code, output = self.invoke()
        self.assertEqual(code, 0)
        self.assertTrue(output["implementation_ready"])
        self.assertIsNone(output["measured_correctness"])
        self.assertIsNone(output["measured_performance"])

    def test_unknown_can_proceed_after_response_without_relabeling(self):
        self.add_risk()
        cost = self.record["geometry_groups"][0]["costs"]["dma_calls"]
        cost.update(status="unknown", estimate=None, basis="Opaque native primitive internals")
        self.sign()
        code, output = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(output["performance_feasibility"], "unknown")

    def test_high_risk_retains_label_after_acceptance(self):
        self.add_risk()
        self.record["review"]["performance_feasibility"] = "high_risk"
        code, output = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(output["performance_feasibility"], "high_risk")

    def test_open_finding_requires_revision_even_if_proceed_declared(self):
        self.add_risk("open")
        code, output = self.invoke()
        self.assertEqual(code, 2)
        self.assertFalse(output["implementation_ready"])

    def test_risk_cannot_be_closed_without_author_response(self):
        self.add_risk()
        self.record["findings"][0]["author_response"] = ""
        self.sign()
        self.assertEqual(self.invoke()[0], 2)

    def test_stale_assessment_is_rejected_for_route_cost_or_response_change(self):
        self.add_risk()
        for key in ("route", "cost", "response"):
            with self.subTest(key=key):
                original = json.loads(json.dumps(self.record))
                if key == "route":
                    self.record["route_options"][0]["primitive"] = "Different route"
                    self.record["geometry_groups"][0]["selected_route"] = "Different route"
                elif key == "cost":
                    self.record["geometry_groups"][0]["costs"]["dma_calls"]["estimate"] = 999
                else:
                    self.record["findings"][0]["author_response"] = "Different response"
                code, output = self.invoke()
                self.assertEqual(code, 2)
                self.assertIn("fingerprint", output["error"])
                self.record = original

    def test_changed_artifact_requires_current_identity(self):
        for name in self.record["artifacts"]:
            with self.subTest(name=name):
                path = self.root / self.record["artifacts"][name]["path"]
                original = path.read_bytes()
                path.write_bytes(b"changed")
                self.assertEqual(self.invoke()[0], 2)
                path.write_bytes(original)

    def test_same_declared_actor_is_rejected(self):
        self.record["reviewer"] = self.record["author"]
        self.sign()
        self.assertEqual(self.invoke()[0], 2)

    def test_undeclared_selected_route_is_rejected(self):
        self.record["geometry_groups"][0]["selected_route"] = "Undeclared primitive"
        self.sign()
        self.assertEqual(self.invoke()[0], 2)

    def test_selected_unsupported_route_is_rejected(self):
        self.record["route_options"][0]["support_status"] = "unsupported"
        self.sign()
        self.assertEqual(self.invoke()[0], 2)

    def test_unselected_unsupported_alternative_does_not_block(self):
        alternative = dict(self.record["route_options"][0], primitive="Rejected alternative",
                           support_status="unsupported", selection_reason="Unsupported fixture shape")
        self.record["route_options"].append(alternative)
        self.sign()
        self.assertEqual(self.invoke()[0], 0)

    def test_selected_unknown_requires_linked_finding(self):
        self.record["route_options"][0]["support_status"] = "unknown"
        self.sign()
        self.assertEqual(self.invoke()[0], 2)
        self.add_risk()
        self.assertEqual(self.invoke()[0], 2)  # An unrelated/general risk is insufficient.
        self.record["route_options"][0]["support_finding_id"] = "missing"
        self.sign()
        self.assertEqual(self.invoke()[0], 2)

    def test_selected_unknown_can_proceed_with_linked_accepted_risk(self):
        self.add_risk()
        option = self.record["route_options"][0]
        option.update(support_status="unknown", support_finding_id="opaque")
        self.sign()
        code, output = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(output["performance_feasibility"], "unknown")
        self.assertEqual(option["support_status"], "unknown")

    def test_ambiguous_duplicate_primitive_names_are_rejected(self):
        self.record["route_options"].append(dict(self.record["route_options"][0]))
        self.sign()
        self.assertEqual(self.invoke()[0], 2)

    def test_missing_cost_dimension_is_rejected(self):
        del self.record["geometry_groups"][0]["costs"]["dma_granularity"]
        self.sign()
        self.assertEqual(self.invoke()[0], 2)

    def test_unreviewed_finding_is_rejected(self):
        self.add_risk()
        self.record["review"]["findings"] = []
        self.assertEqual(self.invoke()[0], 2)

    def test_unknown_without_explicit_finding_is_rejected(self):
        self.record["review"]["performance_feasibility"] = "unknown"
        self.assertEqual(self.invoke()[0], 2)

    def test_revise_or_blocked_is_not_ready(self):
        self.record["review"]["decision"] = "revise"
        self.assertEqual(self.invoke()[0], 2)
        self.add_risk()
        self.record["review"].update(decision="proceed", correctness_feasibility="blocked")
        self.assertEqual(self.invoke()[0], 2)

    def test_digest_only_is_not_permission_and_template_is_invalid(self):
        code, output = self.invoke(self.template, "--assessment-digest")
        self.assertEqual(code, 0)
        self.assertFalse(output["implementation_ready"])
        self.assertEqual(self.invoke(self.template)[0], 2)

    def test_invalid_root_and_nonfinite_cost_are_rejected(self):
        self.assertEqual(self.invoke([])[0], 2)
        self.record["geometry_groups"][0]["costs"]["dma_calls"]["estimate"] = float("inf")
        self.assertEqual(self.invoke()[0], 2)

    def test_formula_is_not_executed(self):
        marker = self.root / "should-not-exist"
        self.record["geometry_groups"][0]["costs"]["dma_calls"]["estimate"] = (
            f"__import__('pathlib').Path({str(marker)!r}).touch()"
        )
        self.sign()
        self.assertEqual(self.invoke()[0], 0)
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
