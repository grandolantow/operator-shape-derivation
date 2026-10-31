"""Offline score-admission regressions against an external CANNBot checkout."""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SKILL = Path(__file__).resolve().parents[1] / "skills/ascend-op-workflow"
PACKAGE = SKILL.parent.parent
CANNBOT_ROOT = Path(os.environ["CANNBOT_SOURCE_ROOT"]).resolve() if os.environ.get("CANNBOT_SOURCE_ROOT") else None
WM = (CANNBOT_ROOT / "plugins-community/ops-perf-evolution/skills/evolution-world-model/scripts"
      if CANNBOT_ROOT else None)
sys.path.insert(0, str(SKILL / "scripts/cannbot"))
import world_model_adapter as adapter
import reserve_nodes


@unittest.skipUnless(CANNBOT_ROOT, "CANNBOT_SOURCE_ROOT is not set")
class AdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not WM.is_dir() or not (WM / "wm_ops.py").is_file():
            raise FileNotFoundError(f"CANNBot world-model scripts not found: {WM}")
        cls.native = adapter.load_native(WM)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.score = 0.5301047980464804
        self.wm = {
            "kernel_summary": "synthetic control-flow fixture; not measured",
            "baseline_performance": {"speedup": self.score},
            "best_score": self.score, "stagnation_count": 0,
            "stagnation_count_vs_base": 0, "open_questions": [],
            "discovered_strategies": [],
            "session": {"session_id": "fixture", "start_time": "fixture",
                        "evo_dir": str(self.root), "op_name": "fixture",
                        "requested_rounds": 1, "actual_rounds_completed": 0},
            "decision_tree": {"nodes": {
                "root": {"id": "root", "parent_id": None, "status": "completed",
                         "score": self.score, "children": ["n1"],
                         "solution_ref": "frozen-G", "mode": "open_exploration"},
                "n1": {"id": "n1", "parent_id": "root", "status": "open",
                       "score": None, "children": [], "strategy_combination": [],
                       "mode": "open_exploration", "description": "fixture hypothesis",
                       "optimization_type": "algorithm", "difficulty": 2,
                       "depth": 1, "retry_count": 0, "solution_ref": None},
            }},
        }
        self.path = self.root / "world_model.json"
        self.selection = self.root / "selections.json"
        self.mapping = self.root / "round_1/parallel_map.json"
        self.path.write_text(json.dumps(self.wm), encoding="utf-8")
        self.selection.write_text(json.dumps([{"parallel_index": 0, "node_id": "n1"}]), encoding="utf-8")

    def test_subunit_score_is_explicit_and_does_not_change_native_or_data(self):
        before = copy.deepcopy(self.wm)
        native_errors = self.native.validate(self.wm)
        self.assertEqual(len(native_errors), 1)
        self.assertFalse(adapter.validate(self.wm, self.native)["valid"])
        result = adapter.validate(self.wm, self.native, "pytorch")
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["native_errors"], native_errors)
        self.assertEqual(self.wm, before)
        self.assertEqual(self.native.validate(self.wm), native_errors)

    def test_invalid_scores_never_pass(self):
        for score in (0, -1, None, True, False, float("nan"), float("inf"), "0.53"):
            with self.subTest(score=score):
                self.wm["best_score"] = score
                self.assertFalse(adapter.validate(self.wm, self.native, "pytorch")["valid"])

    def test_other_invariants_still_block(self):
        changes = [
            lambda wm: wm["decision_tree"]["nodes"]["n1"].update(parent_id="absent"),
            lambda wm: wm["decision_tree"]["nodes"]["n1"].update(status="invented"),
            lambda wm: wm["session"].update(session_id=""),
            lambda wm: wm.update(stagnation_count=-1),
        ]
        for change in changes:
            wm = copy.deepcopy(self.wm)
            change(wm)
            report = adapter.validate(wm, self.native, "pytorch")
            self.assertFalse(report["valid"])
            self.assertEqual(len(report["native_errors"]), 2)
            self.assertEqual(len(report["errors"]), 1)

    def test_unknown_native_errors_are_not_filtered(self):
        class FutureNative:
            @staticmethod
            def validate(wm):
                return ["Invariant 2 FAIL: changed contract"]
        self.assertFalse(adapter.validate(self.wm, FutureNative(), "pytorch")["valid"])

    def reserve(self, base="pytorch"):
        return reserve_nodes.reserve(self.path, self.selection, self.mapping, WM, base)

    def test_reservation_persists_identity_and_rejects_reentry(self):
        self.assertEqual(self.reserve(), {"0": "n1"})
        stored = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(stored["best_score"], self.score)
        self.assertEqual(stored["decision_tree"]["nodes"]["root"]["solution_ref"], "frozen-G")
        self.assertEqual(stored["decision_tree"]["nodes"]["n1"]["status"], "in_progress")
        before = self.path.read_bytes(), self.mapping.read_bytes()
        with self.assertRaisesRegex(ValueError, "already reserved"):
            self.reserve()
        self.assertEqual((self.path.read_bytes(), self.mapping.read_bytes()), before)

    def test_rejected_reservations_do_not_write(self):
        for selection in ([{"parallel_index": 0, "node_id": "free_0"}],
                          [{"parallel_index": 0, "node_id": "n1"}] * 2):
            self.selection.write_text(json.dumps(selection), encoding="utf-8")
            before = self.path.read_bytes()
            with self.assertRaises(ValueError):
                self.reserve()
            self.assertFalse(self.mapping.exists())
            self.assertEqual(self.path.read_bytes(), before)

    def test_native_mode_keeps_original_floor(self):
        with self.assertRaisesRegex(ValueError, "Invariant 2"):
            self.reserve("native")
        self.assertFalse(self.mapping.exists())

    def test_select_works_from_slow_root(self):
        selected = self.native.select_nodes(copy.deepcopy(self.wm), 1)
        self.assertEqual(selected[0]["node_id"], "n1")

    def test_native_refine_keeps_subunit_scores_and_excludes_precision_failure(self):
        for score, precision in ((0.4, True), (0.8, True), (1.2, True), (3.0, False)):
            with self.subTest(score=score, precision=precision):
                wm = copy.deepcopy(self.wm)
                lane = self.root / "round_1/parallel_0"
                lane.mkdir(parents=True, exist_ok=True)
                result = {"fixture": True, "comparison": {
                    "compilation_success": True, "precision_passed": precision,
                    "speedup": 99, "ref_base": "pytorch",
                    "base_time_ms": 1.0, "gen_time_ms": 1.0 / score},
                    "evolved": {"pipeline": None}}
                (lane / "evaluation_results.json").write_text(json.dumps(result), encoding="utf-8")
                (lane / "performance.json").write_text(json.dumps({
                    "geomean_ref_us": score * 100, "geomean_asc_us": 100}), encoding="utf-8")
                (self.root / "baseline_evaluation.json").write_text(
                    '{"base_time_ms_avg":999}', encoding="utf-8")
                self.native.refine(wm, 1, str(lane.parent), {"0": "n1"})
                node = wm["decision_tree"]["nodes"]["n1"]
                self.assertEqual(node["status"], "passed" if precision else "failed")
                if precision:
                    self.assertAlmostEqual(node["score"], score)
                self.assertAlmostEqual(wm["best_score"], round(max(self.score, score if precision else 0), 4))
                self.assertEqual(wm["decision_tree"]["nodes"]["root"]["score"], self.score)
                self.assertTrue(adapter.validate(wm, self.native, "pytorch")["valid"])

    def test_cli_exposes_native_verdict_and_reserves_with_same_contract(self):
        scripts = SKILL / "scripts/cannbot"
        result = subprocess.run([sys.executable, "-B", str(scripts / "world_model_adapter.py"),
            "--wm-scripts", str(WM), "--path", str(self.path), "--score-base", "pytorch"],
            capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["native_errors"])
        result = subprocess.run([sys.executable, "-B", str(scripts / "reserve_nodes.py"),
            "--wm-scripts", str(WM), "--wm-path", str(self.path), "--selections", str(self.selection),
            "--parallel-map", str(self.mapping), "--score-base", "pytorch"],
            capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"0": "n1"})


if __name__ == "__main__":
    unittest.main()
