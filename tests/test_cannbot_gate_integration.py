"""Offline generator-gate regressions against an external CANNBot checkout."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SKILL = Path(__file__).resolve().parents[1] / "skills/ascend-op-workflow"
PACKAGE = SKILL.parent.parent
CANNBOT_ROOT = Path(os.environ["CANNBOT_SOURCE_ROOT"]).resolve() if os.environ.get("CANNBOT_SOURCE_ROOT") else None
PLUGIN = (CANNBOT_ROOT / "plugins-community/tilelang2ascendc-ops-generator"
          if CANNBOT_ROOT else None)
sys_path = str(SKILL / "scripts/cannbot")
import sys
sys.path.insert(0, sys_path)
import generator_gate as gate


@unittest.skipUnless(CANNBOT_ROOT, "CANNBOT_SOURCE_ROOT is not set")
class GateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        required = (PLUGIN / "hooks/doc_gate.py", PLUGIN / "hooks/skill_script_hook.py")
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise FileNotFoundError("CANNBot generator-gate sources not found: " + ", ".join(missing))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name).resolve()
        self.doc, self.hook = gate.modules(self.workspace, CANNBOT_ROOT)

    def decision(self, mode, tool, **data):
        result = gate.event_gate(self.workspace, mode, {"tool_name": tool, "tool_input": data}, self.doc)
        return result["hookSpecificOutput"]["permissionDecision"]

    def cover_docs(self):
        for category in self.doc.FOUNDATIONAL_CATEGORIES.values():
            path = self.workspace / category["example"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("Synthetic fixture", encoding="utf-8")
            self.decision("post", "Read", file_path=str(path))

    def test_document_and_precision_denials_are_visible(self):
        kernel = self.workspace / "output/kernel/op_kernel/op.cpp"
        self.assertEqual(self.decision("pre", "Write", file_path=str(kernel)), "deny")
        self.cover_docs()
        self.assertEqual(self.decision("pre", "Write", file_path=str(kernel)), "allow")
        self.hook._update_precision_gate("D", "Result: fail\nmax_abs_diff=1", str(kernel.parent))
        self.assertEqual(self.decision("pre", "Edit", file_path=str(kernel)), "deny")
        self.decision("skill-post", "Skill", skill="ascendc-precision-debug")
        self.assertEqual(self.decision("pre", "Edit", file_path=str(kernel)), "allow")

    def test_tuning_alias_and_budget(self):
        self.hook._update_precision_gate("D", "Result: fail", "output")
        with self.assertRaises(ValueError):
            self.decision("skill-post", "Skill", skill="tilelang2ascend-precision-tuning")
        for _ in range(7):
            self.decision("skill-post", "Skill", skill="ascendc-precision-debug")
        with self.assertRaises(ValueError):
            self.decision("skill-post", "Skill", skill="ascendc-precision-debug")
        for _ in range(5):
            self.decision("skill-post", "Skill", skill="tilelang2ascend-precision-tuning")
        self.assertEqual(self.doc.read_precision_state()["tune_call_count"], 5)
        with self.assertRaises(ValueError):
            self.decision("skill-post", "Skill", skill="tilelang2ascend-precision-tuning")

    def test_no_false_pass(self):
        cases = [
            (1, "Result: pass", "", "A"),
            (0, "prose PASS", "", "UNKNOWN"),
            (0, "Result: fail\nResult: pass", "", "UNKNOWN"),
            (0, "Result: pass", "CMake Error: broken", "A"),
            (1, "Result: fail\nmax_abs_diff=0.5", "", "D"),
            (0, "INFO: Result: pass", "", "PASS"),
        ]
        for code, stdout, stderr, expected in cases:
            with self.subTest(code=code, stdout=stdout):
                self.assertEqual(gate.classify("ascendc", code, stdout, stderr, self.hook), expected)

    def test_a_unknown_preserve_precision_lock_and_counters(self):
        self.hook._update_precision_gate("D", "Result: fail", "output")
        self.decision("skill-post", "Skill", skill="ascendc-precision-debug")
        for classification in ("A", "UNKNOWN"):
            gate.persist_result(self.hook, classification, "", "output", "fixture.json")
            state = self.doc.read_precision_state()
            self.assertTrue(state["d_class_active"])
            self.assertEqual(state["debug_call_count"], 1)
            self.assertEqual(state["edits_allowed"], 0)

    def test_invalid_events_paths_and_state_fail_closed(self):
        with self.assertRaises(ValueError):
            self.decision("pre", "Bash", command="anything")
        with self.assertRaises(ValueError):
            self.decision("pre", "Write", file_path=str(self.workspace.parent / "escape.cpp"))
        with self.assertRaises(ValueError):
            self.decision("post", "Read", file_path=str(self.workspace / "missing.md"))
        Path(self.doc.PRECISION_GATE_FILE).write_text("invalid json", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            gate.modules(self.workspace, CANNBOT_ROOT)

    def test_modules_rejects_workspace_inside_checkout_before_writing(self):
        workspace = PLUGIN / "skills/tilelang2ascend-translator"
        state_dir = workspace / ".cannbot"

        def snapshot():
            if not state_dir.exists():
                return None
            return tuple((path.relative_to(state_dir).as_posix(), path.read_bytes())
                         for path in sorted(state_dir.rglob("*")) if path.is_file())

        before_exists = state_dir.exists()
        before_state = snapshot()
        with self.assertRaises(ValueError):
            gate.modules(workspace, CANNBOT_ROOT)
        self.assertEqual(state_dir.exists(), before_exists)
        self.assertEqual(snapshot(), before_state)

    def test_run_records_complete_failure_output_and_exit(self):
        target = self.workspace / "output"
        target.mkdir()
        script = self.hook._workflow_plugin / "skills/tilelang2ascend-translator/scripts/verification_ascendc.py"
        raw = b"x" * 20000 + b"\nResult: pass\n"

        def fixture_run(argv, **kwargs):
            kwargs["stdout"].write(raw)
            kwargs["stderr"].write(b"fixture nonzero exit")
            return subprocess.CompletedProcess(argv, 9)

        with patch.dict(os.environ, {"ASCEND_RT_VISIBLE_DEVICES": "0"}), patch.object(gate.subprocess, "run", side_effect=fixture_run):
            result = gate.run_validation(self.workspace, ["python", str(script), str(target)], self.hook)
        self.assertFalse(result["passed"])
        self.assertEqual(result["returncode"], 9)
        self.assertEqual(Path(result["stdout"]).read_bytes(), raw)
        self.assertEqual(self.doc.read_precision_state()["last_classification"], "A")

    def test_unknown_script_rejected_before_execution(self):
        with patch.object(gate.subprocess, "run") as runner:
            with self.assertRaises(ValueError):
                gate.run_validation(self.workspace, ["bash", "evaluate_tilelang.sh", str(self.workspace)], self.hook)
            runner.assert_not_called()

    def test_same_named_validator_outside_checkout_rejected_before_execution(self):
        target = self.workspace / "output"
        target.mkdir()
        validator = self.workspace / "external-copy/verification_ascendc.py"
        validator.parent.mkdir()
        validator.write_text("# fixture copy, not the configured validator", encoding="utf-8")
        with patch.dict(os.environ, {"ASCEND_RT_VISIBLE_DEVICES": "0"}), patch.object(gate.subprocess, "run") as runner:
            with self.assertRaises(ValueError):
                gate.run_validation(self.workspace, ["python", str(validator), str(target)], self.hook)
            runner.assert_not_called()

    def linked_directory(self, target, link):
        if os.name == "nt":
            command = "New-Item -ItemType Junction -Path '{}' -Target '{}' | Out-Null".format(str(link).replace("'", "''"), str(target).replace("'", "''"))
            subprocess.run(["powershell", "-NoProfile", "-Command", command], check=True, capture_output=True)
        else:
            link.symlink_to(target, target_is_directory=True)

    def test_logical_devkit_link_counts_all_categories(self):
        checkout = self.workspace / "existing-docs"
        checkout.mkdir()
        self.linked_directory(checkout, self.workspace / "asc-devkit")
        for category in self.doc.FOUNDATIONAL_CATEGORIES.values():
            relative = Path(category["example"]).relative_to("asc-devkit")
            real = checkout / relative
            real.parent.mkdir(parents=True, exist_ok=True)
            real.write_text("fixture", encoding="utf-8")
            self.decision("post", "Read", file_path=str(self.workspace / "asc-devkit" / relative))
        self.assertEqual(len(self.doc.get_covered_categories(self.doc.read_state()["docs_read"])), 4)

    def successful_record(self, full=False, expected=2):
        target = self.workspace / "output"
        target.mkdir(exist_ok=True)
        for name in ("model.py", "model_new_ascendc.py", "kernel/op.cpp"):
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture source", encoding="utf-8")
        (target / "cases.json").write_text("[1,2]", encoding="utf-8")
        manifest = None
        if full:
            manifest = self.workspace / ".cannbot/full-manifest.json"
            manifest.write_text(json.dumps({"scope": "full", "expected_cases": expected, "files": {
                name: gate.sha256(target / name) for name in ("model.py", "cases.json")
            }}), encoding="utf-8")
        script = self.hook._workflow_plugin / "skills/tilelang2ascend-translator/scripts/verification_ascendc.py"

        def fixture_run(argv, **kwargs):
            kwargs["stdout"].write(b"case[0]: matched\ncase[1]: matched\nResult: pass\n")
            return subprocess.CompletedProcess(argv, 0)

        with patch.dict(os.environ, {"ASCEND_RT_VISIBLE_DEVICES": "0"}), patch.object(gate.subprocess, "run", side_effect=fixture_run):
            return gate.run_validation(self.workspace, ["python", str(script), str(target)], self.hook, expected, manifest)

    def test_check_rejects_stale_source_reference_inputs_and_missing_full(self):
        record = self.successful_record()
        self.assertTrue(gate.check_validation(self.workspace, self.hook)["passed"])
        self.assertFalse(gate.check_validation(self.workspace, self.hook, True)["passed"])
        for name in ("kernel/op.cpp", "model.py", "cases.json"):
            path = self.workspace / "output" / name
            original = path.read_bytes()
            path.write_bytes(b"modified")
            self.assertFalse(gate.check_validation(self.workspace, self.hook)["passed"])
            path.write_bytes(original)
        self.cover_docs()
        self.decision("pre", "Edit", file_path=str(self.workspace / "output/kernel/op.cpp"))
        self.assertEqual(self.doc.read_precision_state()["last_classification"], "STALE")
        self.assertFalse(gate.check_validation(self.workspace, self.hook)["passed"])

    def test_actual_full_count_and_manifest_required(self):
        result = self.successful_record(full=True)
        self.assertEqual(result["coverage"]["actual_cases"], 2)
        self.assertTrue(gate.check_validation(self.workspace, self.hook, True)["passed"])
        result = self.successful_record(full=True, expected=3)
        self.assertFalse(result["passed"])
        self.assertFalse(gate.check_validation(self.workspace, self.hook, True)["passed"])
        self.assertIsNone(gate.actual_cases("Result: pass", ""))
        self.assertIsNone(gate.actual_cases("case[1]: matched\ncase[2]: matched", ""))

    def test_modified_rawlog_or_full_manifest_rejected(self):
        record = self.successful_record(full=True)
        Path(record["stdout"]).write_text("changed", encoding="utf-8")
        self.assertFalse(gate.check_validation(self.workspace, self.hook, True)["passed"])
        self.successful_record(full=True)
        manifest = self.workspace / ".cannbot/full-manifest.json"
        manifest.write_text("{}", encoding="utf-8")
        self.assertFalse(gate.check_validation(self.workspace, self.hook, True)["passed"])

    def test_check_rejects_record_from_different_cannbot_source(self):
        result = self.successful_record()
        record_path = Path(result["record"])
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["cannbot_source"] = str(PLUGIN.parent / "different-checkout")
        record_path.write_text(json.dumps(record), encoding="utf-8")
        self.assertFalse(gate.check_validation(self.workspace, self.hook)["passed"])

    def test_check_rejects_validator_hash_mismatch(self):
        result = self.successful_record()
        record_path = Path(result["record"])
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["validator_sha256"] = "0" * 64
        record_path.write_text(json.dumps(record), encoding="utf-8")
        self.assertFalse(gate.check_validation(self.workspace, self.hook)["passed"])

    def test_shell_run_binds_local_indirect_validator_identity(self):
        validator_rel = Path(".claude/skills/tilelang2ascend-translator/scripts/verification_ascendc.py")
        validator = self.workspace / validator_rel
        validator.parent.mkdir(parents=True)
        external_validator = self.hook._workflow_plugin / "skills/tilelang2ascend-translator/scripts/verification_ascendc.py"
        validator.write_bytes(external_validator.read_bytes())

        target = self.workspace / "output"
        target.mkdir()
        for name in ("model.py", "model_new_ascendc.py", "kernel/op.cpp"):
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture source", encoding="utf-8")
        (target / "cases.json").write_text("[1]", encoding="utf-8")
        script = self.hook._workflow_plugin / "skills/tilelang2ascend-translator/scripts/evaluate_ascendc.sh"

        def fixture_run(argv, **kwargs):
            kwargs["stdout"].write(b"case[0]: matched\nResult: pass\n")
            return subprocess.CompletedProcess(argv, 0)

        with patch.dict(os.environ, {"ASCEND_RT_VISIBLE_DEVICES": "0", "ASCENDC_SOC_VERSION": "Ascend910B3"}), \
                patch.object(gate.subprocess, "run", side_effect=fixture_run) as runner:
            result = gate.run_validation(self.workspace, ["bash", str(script), str(target)], self.hook)
            self.assertTrue(result["passed"])
            self.assertTrue(gate.check_validation(self.workspace, self.hook)["passed"])

            validator.write_text("# changed local indirect validator", encoding="utf-8")
            self.assertFalse(gate.check_validation(self.workspace, self.hook)["passed"])
            runner.reset_mock()
            with self.assertRaises(ValueError):
                gate.run_validation(self.workspace, ["bash", str(script), str(target)], self.hook)
            runner.assert_not_called()

    def test_gate_run_junction_escape_rejected_without_execution(self):
        with tempfile.TemporaryDirectory() as outside:
            self.linked_directory(Path(outside), self.workspace / ".cannbot/gate-runs")
            target = self.workspace / "output.py"
            target.write_text("fixture", encoding="utf-8")
            script = self.hook._workflow_plugin / "skills/tilelang2ascend-translator/scripts/validate_ascendc_impl.py"
            with patch.object(gate.subprocess, "run") as runner:
                with self.assertRaises(ValueError):
                    gate.run_validation(self.workspace, ["python", str(script), str(target)], self.hook)
                runner.assert_not_called()
            self.assertEqual(list(Path(outside).iterdir()), [])

    def test_cli_denies_and_emits_json(self):
        proc = subprocess.run(
            [os.sys.executable, "-B", str(Path(gate.__file__)), "--cannbot-root", str(CANNBOT_ROOT),
             "--workspace", str(self.workspace), "--mode", "pre"],
            input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(self.workspace / "kernel/op.cpp")}}),
            capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_asc_source_change_invalidates_previous_pass(self):
        self.successful_record()
        self.assertTrue(gate.check_validation(self.workspace, self.hook)["passed"])
        source = self.workspace / "output/kernel/op.asc"
        source.write_text("fixture source", encoding="utf-8")
        self.assertFalse(gate.check_validation(self.workspace, self.hook)["passed"])
        result = self.successful_record()
        self.assertTrue(gate.check_validation(self.workspace, self.hook)["passed"])
        source.write_text("changed source", encoding="utf-8")
        self.assertFalse(gate.check_validation(self.workspace, self.hook)["passed"])


if __name__ == "__main__":
    unittest.main()
