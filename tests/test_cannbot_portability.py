"""Fresh task installation and resource preparation; fixtures never use an NPU."""

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skills/ascend-op-workflow/scripts/cannbot"
SPEC = importlib.util.spec_from_file_location("prepare_cannbot", SCRIPTS / "prepare_workspace.py")
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)


class PortabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="workflow portable ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.checkout = self.root / "external CANNBot"
        self.workspace = self.root / "operator run"
        self.skill_root = self.checkout / "plugins-community/ops-perf-evolution/skills"
        for name in prepare.DEFAULT_SKILLS:
            path = self.skill_root / name
            path.mkdir(parents=True)
            (path / "SKILL.md").write_text(f"fixture {name}\n", encoding="utf-8")
        wm = self.skill_root / "evolution-world-model/scripts/wm_ops.py"
        wm.parent.mkdir()
        wm.write_text(
            "def validate(wm):\n"
            "    score = wm['best_score']\n"
            "    return [f'Invariant 2 FAIL: best_score={score} is less than 1.0'] if score < 1 else []\n",
            encoding="utf-8")

    def snapshot(self):
        return {p.relative_to(self.checkout).as_posix(): p.read_bytes()
                for p in self.checkout.rglob("*") if p.is_file()}

    def invoke(self, *args):
        return subprocess.run([sys.executable, "-B", "-X", "utf8", *map(str, args)],
                              cwd=self.root, capture_output=True, text=True, encoding="utf-8")

    def test_fresh_install_has_executable_helpers_without_local_adapter(self):
        # An independent distribution and task, with no vendor or old adapter.
        distribution = self.root / "workflow distribution"
        distribution.mkdir()
        shutil.copy2(REPO / "install_codex.py", distribution)
        shutil.copytree(REPO / "skills", distribution / "skills",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        self.workspace.mkdir()
        before = self.snapshot()
        result = self.invoke(distribution / "install_codex.py", "--task-dir", self.workspace, "--apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        installed = self.workspace / ".agents/skills/ascend-op-workflow/scripts/cannbot"
        manifest = json.loads((self.workspace / ".agents/ascend-op-workflow-install.json").read_text())
        self.assertIsNone(manifest["cannbot_root"])
        for name in ("world_model_adapter.py", "reserve_nodes.py", "generator_gate.py", "prepare_workspace.py"):
            self.assertEqual((installed / name).read_bytes(), (SCRIPTS / name).read_bytes())
            self.assertEqual(self.invoke(installed / name, "--help").returncode, 0)
        run = self.workspace / "evolution"
        result = self.invoke(installed / "prepare_workspace.py", "--workspace", run,
                             "--cannbot-root", self.checkout)
        self.assertEqual(result.returncode, 0, result.stderr)
        state = run / "world_model.json"
        score = 0.5301047980464804
        state.write_text(json.dumps({"best_score": score, "decision_tree": {"nodes": {
            "n1": {"status": "open"}}}}), encoding="utf-8")
        wm_scripts = run / ".claude/skills/evolution-world-model/scripts"
        report = self.invoke(installed / "world_model_adapter.py", "--wm-scripts", wm_scripts,
                             "--path", state, "--score-base", "pytorch")
        self.assertEqual(report.returncode, 0, report.stderr)
        self.assertTrue(json.loads(report.stdout)["native_errors"])
        selections = run / "selections.json"
        selections.write_text('[{"parallel_index":0,"node_id":"n1"}]', encoding="utf-8")
        mapping = run / "round_1/parallel_map.json"
        result = self.invoke(installed / "reserve_nodes.py", "--wm-scripts", wm_scripts,
                             "--wm-path", state, "--selections", selections,
                             "--parallel-map", mapping, "--score-base", "pytorch")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(mapping.read_text()), {"0": "n1"})
        self.assertEqual(json.loads(state.read_text())["best_score"], score)
        self.assertEqual(before, self.snapshot())

    def test_resume_retains_mutable_resources_and_rejects_changed_source(self):
        before = self.snapshot()
        prepare.prepare(self.workspace, self.checkout)
        mutable = self.workspace / ".claude/skills/evolution-world-model/SKILL.md"
        mutable.write_text("task-owned state\n", encoding="utf-8")
        self.assertEqual(prepare.prepare(self.workspace, self.checkout)["status"], "prepared")
        self.assertEqual(mutable.read_text(), "task-owned state\n")
        self.assertEqual(before, self.snapshot())
        source = self.skill_root / "evolution-world-model/SKILL.md"
        source.write_text("changed upstream\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source changed"):
            prepare.prepare(self.workspace, self.checkout)
        self.assertEqual(mutable.read_text(), "task-owned state\n")

    def test_partial_copy_can_resume_without_publishing_incomplete_resources(self):
        original = prepare.shutil.copytree
        def interrupted(source, destination, **kwargs):
            Path(destination).mkdir(parents=True)
            (Path(destination) / "SKILL.md").write_text("partial", encoding="utf-8")
            raise OSError("fixture interrupted copy")
        with patch.object(prepare.shutil, "copytree", side_effect=interrupted):
            with self.assertRaisesRegex(OSError, "interrupted"):
                prepare.prepare(self.workspace, self.checkout)
        marker = self.workspace / ".cannbot/workspace.json"
        self.assertEqual(json.loads(marker.read_text())["status"], "preparing")
        self.assertFalse((self.workspace / ".claude/skills/evolution-world-model").exists())
        with patch.object(prepare.shutil, "copytree", original):
            result = prepare.prepare(self.workspace, self.checkout)
        self.assertEqual(result["status"], "prepared")
        self.assertTrue(all(item["ready"] for item in result["resources"].values()))

    def test_missing_resource_or_unowned_path_is_rejected_before_writes(self):
        with self.assertRaisesRegex(ValueError, "Missing CANNBot resource"):
            prepare.prepare(self.workspace, self.checkout, ["missing"])
        self.assertFalse(self.workspace.exists())
        target = self.workspace / ".claude/skills/evolution-world-model"
        target.mkdir(parents=True)
        (target / "user.txt").write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(FileExistsError, "Unowned"):
            prepare.prepare(self.workspace, self.checkout)
        self.assertFalse((self.workspace / ".cannbot").exists())

    def test_translator_resource_does_not_require_archived_template_copies(self):
        source = self.checkout / "plugins-community/tilelang2ascendc-ops-generator/skills/tilelang2ascend-translator"
        source.mkdir(parents=True)
        (source / "SKILL.md").write_text("fixture translator\n", encoding="utf-8")
        result = prepare.prepare(self.workspace, self.checkout, ["tilelang2ascend-translator"])
        self.assertEqual(result["status"], "prepared")
        self.assertTrue((self.workspace / ".claude/skills/tilelang2ascend-translator/SKILL.md").is_file())
        self.assertFalse((self.workspace / "workflows").exists())


if __name__ == "__main__":
    unittest.main()
