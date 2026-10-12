"""Windows-friendly task-local Codex installer tests."""

import importlib.util
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


INSTALLER = Path(__file__).resolve().parents[1] / "install_codex.py"
SPEC = importlib.util.spec_from_file_location("install_codex", INSTALLER)
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class InstallCodexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "CANNBot"
        self.task = self.root / "task"
        self.task.mkdir()
        self.gen = self.repo / "plugins-community" / installer.GEN
        self.evo = self.repo / "plugins-community" / installer.EVO
        for plugin in (self.gen, self.evo):
            self.write(plugin / "init.sh", "#!/bin/sh\n")
            (plugin / "agents").mkdir()
        self.write(self.gen / "AGENTS.md", "---\nskills:\n  - common\n  - gen-only\n---\n")
        self.write(self.evo / "AGENTS.md", "---\nskills:\n  - common\n  - evo-only\n---\n")
        for name in ("common", "gen-only", "op-case-generator"):
            self.write(self.repo / "ops" / name / "SKILL.md", name)
        self.write(self.evo / "skills/evo-only/SKILL.md", "evo")
        for name, plugin in (("tilelang2ascendc-kernel-generator", self.gen),
                             ("lingxi-evo", self.evo), ("lingxi-partial", self.evo),
                             ("ops-evo", self.evo), ("ops-partial", self.evo)):
            self.write(plugin / "agents" / f"{name}.md", f"---\nname: {name}\nskills: []\n---\n")
        self.package = self.root / "ascend-op-workflow"
        bundled = self.package / "skills"
        self.workflow = bundled / "ascend-op-workflow"
        self.write(self.workflow / "SKILL.md", "workflow")
        self.write(bundled / "operator-shape-derivation/SKILL.md", "shape")
        package_patch = patch.object(installer, "PACKAGE", self.package)
        package_patch.start()
        self.addCleanup(package_patch.stop)

    def write(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def build(self):
        return installer.plan(self.repo, self.task, self.workflow)

    def test_dry_run_apply_and_idempotence_without_symlinks(self):
        entries, manifest = self.build()
        self.assertFalse(installer.check(self.task, entries, manifest))
        self.assertFalse((self.task / ".agents").exists())
        installer.install(self.task, entries)
        self.assertTrue(installer.check(self.task, entries, manifest))
        copied = self.task / ".agents/skills/operator-shape-derivation/SKILL.md"
        self.assertTrue(copied.is_file())
        self.assertFalse(copied.is_symlink())
        self.assertTrue((self.task / ".agents/skills/op-case-generator/SKILL.md").is_file())
        routing = (self.task / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Claude hooks are not installed", routing)
        self.assertIn("not root SKILL.md", routing)
        self.assertIn("full CANNBot source", routing)
        self.assertIn("full correctness", routing)
        self.assertEqual(json.loads((self.task / installer.MANIFEST).read_text(encoding="utf-8")), manifest)

    def test_missing_dependency_and_collision_fail(self):
        (self.repo / "ops/gen-only/SKILL.md").unlink()
        with self.assertRaisesRegex(installer.InstallError, "Missing required skill"):
            self.build()
        self.write(self.repo / "ops/gen-only/SKILL.md", "gen")
        self.write(self.evo / "skills/common/SKILL.md", "different")
        with self.assertRaisesRegex(installer.InstallError, "Cross-plugin skill collision"):
            self.build()

    def test_existing_unknown_file_is_preserved(self):
        unknown = self.write(self.task / "AGENTS.md", "my own instructions")
        entries, manifest = self.build()
        with self.assertRaisesRegex(installer.InstallError, "unowned"):
            installer.check(self.task, entries, manifest)
        self.assertEqual(unknown.read_text(encoding="utf-8"), "my own instructions")

    def test_modified_managed_file_rejected(self):
        entries, manifest = self.build()
        installer.install(self.task, entries)
        (self.task / ".agents/skills/common/SKILL.md").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(installer.InstallError, "Managed entry changed"):
            installer.check(self.task, entries, manifest)

    def test_required_bundled_shape_skill_missing_fails(self):
        (self.package / "skills/operator-shape-derivation/SKILL.md").unlink()
        with self.assertRaisesRegex(installer.InstallError, "Missing required packaged skill"):
            self.build()

    def test_explicit_workflow_is_installed_instead_of_bundle(self):
        custom = self.write(self.root / "custom-workflow/SKILL.md", "custom workflow")
        entries, manifest = installer.plan(self.repo, self.task, custom.parent)
        self.assertEqual(Path(entries[".agents/skills/ascend-op-workflow"]["source"]), custom.parent.resolve())
        installer.install(self.task, entries)
        self.assertEqual(
            (self.task / ".agents/skills/ascend-op-workflow/SKILL.md").read_text(encoding="utf-8"),
            "custom workflow",
        )
        self.assertTrue(installer.check(self.task, entries, manifest))

    def test_reparse_parent_rejected_even_when_manifest_exists(self):
        entries, manifest = self.build()
        installer.install(self.task, entries)
        original = installer.is_reparse
        with patch.object(installer, "is_reparse", side_effect=lambda path: path == self.task / ".agents" or original(path)):
            with self.assertRaisesRegex(installer.InstallError, "Unsafe destination parent"):
                installer.check(self.task, entries, manifest)

    def test_cli_uses_standalone_package_and_records_external_cannbot(self):
        self.assertFalse((self.repo / "tools").exists())
        with contextlib.redirect_stdout(io.StringIO()):
            result = installer.main(["--cannbot-root", str(self.repo),
                                     "--task-dir", str(self.task), "--apply"])
        self.assertEqual(result, 0)
        manifest = json.loads((self.task / installer.MANIFEST).read_text(encoding="utf-8"))
        self.assertEqual(manifest["workflow_repo_root"], str(self.package.resolve()))
        self.assertEqual(manifest["cannbot_root"], str(self.repo.resolve()))
        self.assertEqual(manifest["workflow_skill"], str(self.workflow.resolve()))
        self.assertEqual(
            manifest["entries"][".agents/skills/operator-shape-derivation"]["source"],
            str((self.package / "skills/operator-shape-derivation").resolve()),
        )
        self.assertIn(str(self.repo.resolve()), manifest["skill_origins"]["gen-only"][0])

    def test_cli_requires_explicit_cannbot_root(self):
        with contextlib.redirect_stderr(io.StringIO()) as errors:
            with self.assertRaises(SystemExit) as raised:
                installer.main(["--task-dir", str(self.task), "--apply"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("--cannbot-root", errors.getvalue())
        self.assertFalse((self.task / ".agents").exists())

    def test_legacy_repo_root_alias_uses_same_external_source(self):
        with contextlib.redirect_stdout(io.StringIO()):
            result = installer.main(["--repo-root", str(self.repo),
                                     "--task-dir", str(self.task), "--apply"])
        self.assertEqual(result, 0)
        manifest = json.loads((self.task / installer.MANIFEST).read_text(encoding="utf-8"))
        self.assertEqual(manifest["cannbot_root"], str(self.repo.resolve()))
        self.assertEqual(manifest["workflow_skill"], str(self.workflow.resolve()))


if __name__ == "__main__":
    unittest.main()
