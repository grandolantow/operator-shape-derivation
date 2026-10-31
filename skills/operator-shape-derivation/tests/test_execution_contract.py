import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("checker", Path(__file__).parents[1] / "scripts/check_execution_contract.py")
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


def quantity(value=4, status="configured", **extra):
    return dict(value=value, status=status, scope="operator input dimension", evidence="test configuration", **extra)


def check(quantities, required, decisions=None):
    return checker.validate_contract({"execution_contract": dict(quantities=quantities, required_for_export=required, decisions=decisions or [])})


def decision(status="pending", **extra):
    return dict(id="choose", quantities=["M"], reason="execution scope is ambiguous", question="Which rank receives these tokens?", status=status, **extra)


class ContractTests(unittest.TestCase):
    def test_plain_matmul(self):
        result = check({name: quantity() for name in ("M", "N", "K")}, ["M", "N", "K"])
        self.assertEqual(result["exit_code"], 0)
        self.assertFalse(result["rule_semantics_verified"])

    def test_assumptions_propagate(self):
        result = check({"total": quantity(16), "local": quantity(8, "assumed", depends_on=["total"], assumptions=["user authorized an even split"]), "M": quantity(8, "derived", depends_on=["local"])}, ["M"])
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["quantities"]["M"]["assumptions"][0]["quantity"], "local")
        self.assertEqual(result["quantities"]["local"]["declared_status"], "assumed")

    def test_assumption_cannot_be_labeled_observed(self):
        qs = {
            "chosen": quantity(8, "assumed", assumptions=["user selected test distribution"]),
            "M": quantity(8, "observed", depends_on=["chosen"]),
        }
        result = check(qs, ["M"])
        self.assertEqual(result["exit_code"], 1)
        self.assertIn("observed-depends-on-assumption", [i["code"] for i in result["issues"]])

    def test_ambiguous_and_missing_decision(self):
        q = quantity(None, "unknown")
        q["scope"] = "未确定"
        self.assertEqual(check({"M": q}, ["M"], [decision()])["exit_code"], 2)
        result = check({"M": q}, ["M"])
        self.assertIn("missing-decision", [i["code"] for i in result["issues"]])
        self.assertEqual(result["exit_code"], 2)

    def test_upstream_decision_covers_conditional_output(self):
        qs = {
            "M": quantity(None, "unknown"),
            "output": quantity(None, "conditional", depends_on=["M"]),
        }
        result = check(qs, ["output"], [decision()])
        self.assertEqual(result["exit_code"], 2)
        self.assertEqual(result["quantities"]["output"]["pending_decisions"], ["choose"])
        self.assertNotIn("missing-decision", [i["code"] for i in result["issues"]])

    def test_human_resolution(self):
        result = check({"M": quantity(8)}, ["M"], [decision("resolved", evidence="user selected per-rank batch 8")])
        self.assertEqual(result["exit_code"], 0)

    def test_independent_unknown(self):
        result = check({"M": quantity(), "other": quantity(None, "unknown")}, ["M"])
        self.assertEqual(result["exit_code"], 0)
        self.assertTrue(result["quantities"]["M"]["available"])
        self.assertFalse(result["quantities"]["other"]["available"])

    def test_missing_dependency_and_cycle(self):
        for qs in ({"M": quantity(4, "derived", depends_on=["absent"])}, {"M": quantity(4, "derived", depends_on=["N"]), "N": quantity(4, "derived", depends_on=["M"])}):
            self.assertEqual(check(qs, ["M"])["exit_code"], 1)

    def test_known_cannot_erase_unknown(self):
        result = check({"M": quantity(None, "conditional"), "result": quantity(4, "derived", depends_on=["M"])}, ["result"], [decision()])
        self.assertEqual(result["exit_code"], 1)
        self.assertFalse(result["quantities"]["result"]["available"])
        self.assertEqual(result["quantities"]["result"]["pending_decisions"], ["choose"])
        self.assertEqual(result["quantities"]["result"]["unresolved_quantities"], ["M"])

    def test_scope_and_stale_value(self):
        for scope in (None, "", "unknown", "ambiguous"):
            q = quantity()
            q["scope"] = scope
            self.assertEqual(check({"M": q}, ["M"])["exit_code"], 1)
        self.assertEqual(check({"M": quantity(8, "unknown")}, ["M"], [decision()])["exit_code"], 1)

    def test_pending_propagation_and_external_rule(self):
        qs = {"M": quantity(), "result": quantity(8, "derived", depends_on=["M"])}
        self.assertEqual(check(qs, ["result"], [decision()])["exit_code"], 2)
        self.assertEqual(check({"M": quantity(8, "derived", rule_evidence="external specification equation 3")}, ["M"])["exit_code"], 0)


if __name__ == "__main__":
    unittest.main()
