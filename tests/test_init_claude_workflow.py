"""Task-local bootstrap safety checks using a small CANNBot fixture."""

import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SPEC = importlib.util.spec_from_file_location("bootstrap", Path(__file__).resolve().parents[1] / "init_claude_workflow.py")
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "CANNBot"
        self.task = self.root / "task with space"
        self.task.mkdir()
        self.workflow = self.root / "workflow-skill"
        self.write(self.workflow / "SKILL.md", "# Workflow\n")
        self.package = self.root / "package"
        self.write(self.package / "skills/operator-shape-derivation/SKILL.md", "# Shapes\n")
        patcher = mock.patch.object(bootstrap, "PACKAGE", self.package)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.gen = self.repo / "plugins-community" / bootstrap.GEN
        self.evo = self.repo / "plugins-community" / bootstrap.EVO
        for plugin in (self.gen, self.evo):
            self.write(plugin / "init.sh", "#!/bin/sh\n")
            (plugin / "agents").mkdir()
            (plugin / "hooks").mkdir()
        self.write(self.gen / "AGENTS.md", "---\nskills:\n  - common\n  - gen-only\n---\n")
        self.write(self.evo / "AGENTS.md", "---\nskills:\n  - common\n  - evo-only\n---\n")
        for name in ("common", "gen-only"):
            self.write(self.repo / "ops" / name / "SKILL.md", name)
        self.write(self.repo / "ops/op-case-generator/SKILL.md", "cases")
        self.write(self.evo / "skills/evo-only/SKILL.md", "evo")
        for name, plugin in (("tilelang2ascendc-kernel-generator", self.gen),
                             ("lingxi-evo", self.evo), ("lingxi-partial", self.evo),
                             ("ops-evo", self.evo), ("ops-partial", self.evo)):
            self.write(plugin / "agents" / f"{name}.md", f"---\nname: {name}\nskills: []\n---\n")
        self.write(self.gen / "hooks/run-hook.cmd", "#!/bin/sh\n")
        self.write(self.evo / "hooks/loop-stop.sh", "#!/bin/sh\n")
        self.write(self.gen / "hooks/hooks.json", json.dumps({"hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command": '"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd" start', "async": False}]}]
        }}))
        self.write(self.evo / "hooks/hooks.json", json.dumps({"hooks": {
            "Stop": [{"hooks": [{"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/.claude/hooks/loop-stop.sh", "timeout": 60}]}]
        }}))
        self.write(self.gen / "workflows/README.md", "workflows")

    def write(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def build(self):
        return bootstrap.plan(self.repo, self.task, self.workflow)

    @unittest.skipIf(os.name == "nt", "Windows host lacks symlink privilege; apply runs in Linux container")
    def test_dry_run_apply_idempotence_and_hook_merge(self):
        entries, manifest = self.build()
        self.assertFalse(bootstrap.check_existing(self.task, entries, manifest))
        self.assertFalse((self.task / ".claude").exists())
        bootstrap.apply(self.task, entries)
        self.assertTrue(bootstrap.check_existing(self.task, entries, manifest))
        settings = json.loads((self.task / ".claude/settings.json").read_text(encoding="utf-8"))
        self.assertEqual(set(settings["hooks"]), {"SessionStart", "Stop"})
        self.assertIn("CLAUDE_PROJECT_DIR=", settings["hooks"]["Stop"][0]["hooks"][0]["command"])
        self.assertIn("'", settings["hooks"]["Stop"][0]["hooks"][0]["command"])
        self.write(self.task / ".claude/runtime/generation/hooks/__pycache__/run.pyc", "cache")
        self.assertTrue(bootstrap.check_existing(self.task, entries, manifest))

    def test_missing_dependency_and_cross_plugin_collision_fail(self):
        (self.repo / "ops/gen-only/SKILL.md").unlink()
        with self.assertRaisesRegex(bootstrap.BootstrapError, "Missing required skill"):
            self.build()
        self.write(self.repo / "ops/gen-only/SKILL.md", "gen")
        self.write(self.evo / "skills/common/SKILL.md", "different")
        with self.assertRaisesRegex(bootstrap.BootstrapError, "Cross-plugin skill collision"):
            self.build()

    def test_explicit_workflow_dependencies_are_required(self):
        (self.repo / "ops/op-case-generator/SKILL.md").unlink()
        with self.assertRaisesRegex(bootstrap.BootstrapError, "Missing required workflow skill"):
            self.build()
        self.write(self.repo / "ops/op-case-generator/SKILL.md", "cases")
        (self.package / "skills/operator-shape-derivation/SKILL.md").unlink()
        with self.assertRaisesRegex(bootstrap.BootstrapError, "Missing required workflow skill"):
            self.build()

    def test_unknown_existing_entry_is_preserved(self):
        unknown = self.write(self.task / ".claude/settings.json", "private settings")
        entries, manifest = self.build()
        with self.assertRaisesRegex(bootstrap.BootstrapError, "unowned entry"):
            bootstrap.check_existing(self.task, entries, manifest)
        self.assertEqual(unknown.read_text(encoding="utf-8"), "private settings")

    def test_registered_existing_workflow_source(self):
        source = self.task / ".claude/skills/ascend-op-workflow"
        self.write(source / "SKILL.md", "# Workflow")
        entries, manifest = bootstrap.plan(self.repo, self.task, source)
        self.assertEqual(entries[".claude/skills/ascend-op-workflow"]["kind"], "existing_source")
        self.assertFalse(bootstrap.check_existing(self.task, entries, manifest))

    @unittest.skipIf(os.name == "nt", "Literal backslash filenames are a Linux staging failure")
    def test_reject_literal_windows_transfer_paths(self):
        source = self.task / ".claude/skills/ascend-op-workflow"
        self.write(source / "SKILL.md", "# Workflow")
        self.write(source / "references\\contract.md", "misplaced")
        with self.assertRaisesRegex(bootstrap.BootstrapError, "literal Windows separators"):
            bootstrap.plan(self.repo, self.task, source)

    @unittest.skipIf(os.name == "nt", "Windows host lacks symlink privilege; apply runs in Linux container")
    def test_attention_overlay_hash_matches_installed_copy(self):
        self.write(self.gen / "AGENTS.md", "---\nskills:\n  - common\n  - tilelang2ascend-tilelang-designer\n---\n")
        self.write(self.gen / "skills/tilelang2ascend-tilelang-designer/SKILL.md", "designer")
        self.write(self.gen / "skills/tilelang2ascend-translator/references/attention-patterns/a.md", "attention")
        entries, manifest = self.build()
        rel = ".claude/skills/tilelang2ascend-tilelang-designer"
        self.assertEqual(entries[rel]["kind"], "copytree")
        bootstrap.apply(self.task, entries)
        self.assertTrue(bootstrap.check_existing(self.task, entries, manifest))

    @unittest.skipIf(os.name == "nt", "Windows host lacks symlink privilege")
    def test_source_tree_internal_links_are_hashed_without_following_and_escape_fails(self):
        devkit = self.gen / "asc-devkit"
        self.write(devkit / ".agent/README.md", "inside")
        linked = devkit / ".claude/README.md"
        linked.parent.mkdir(parents=True)
        linked.symlink_to("../.agent/README.md")
        first = bootstrap.hash_tree(devkit)
        self.assertEqual(first, bootstrap.hash_tree(devkit))
        linked.unlink()
        linked.symlink_to("../.agent/README.md")
        self.assertEqual(first, bootstrap.hash_tree(devkit))
        linked.unlink()
        linked.symlink_to(self.workflow / "SKILL.md")
        with self.assertRaisesRegex(bootstrap.BootstrapError, "escapes root"):
            bootstrap.hash_tree(devkit)

    @unittest.skipIf(os.name == "nt", "Symlink apply runs in Linux container")
    def test_copytree_preserves_internal_link_and_rejects_link_replacement(self):
        (self.gen / "hooks/alias.cmd").symlink_to("run-hook.cmd")
        entries, manifest = self.build()
        bootstrap.apply(self.task, entries)
        copied = self.task / ".claude/runtime/generation/hooks"
        self.assertTrue((copied / "alias.cmd").is_symlink())
        self.assertTrue(bootstrap.check_existing(self.task, entries, manifest))
        shutil.rmtree(copied)
        copied.symlink_to(self.gen / "hooks", target_is_directory=True)
        with self.assertRaisesRegex(bootstrap.BootstrapError, "Managed copy changed type"):
            bootstrap.check_existing(self.task, entries, manifest)

    @unittest.skipIf(os.name == "nt", "Symlink apply runs in Linux container")
    def test_managed_file_cannot_be_replaced_by_link(self):
        entries, manifest = self.build()
        bootstrap.apply(self.task, entries)
        settings = self.task / ".claude/settings.json"
        saved = self.task / "settings-copy.json"
        saved.write_bytes(settings.read_bytes())
        settings.unlink()
        settings.symlink_to(saved)
        with self.assertRaisesRegex(bootstrap.BootstrapError, "Managed file changed type"):
            bootstrap.check_existing(self.task, entries, manifest)


if __name__ == "__main__":
    unittest.main()
