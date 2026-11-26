"""Exercise CANNBot source resolution with local Git repositories."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skills/ascend-op-workflow/scripts/cannbot"
SPEC = importlib.util.spec_from_file_location("prepare", SCRIPTS / "prepare_workspace.py")
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)


@unittest.skipUnless(shutil.which("git"), "Git is required for source resolution")
class SourceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="cannbot source ")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.task = self.root / "task"
        self.task.mkdir()
        self.env = os.environ | {
            "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.com",
            "GIT_CONFIG_COUNT": "2",
            "GIT_CONFIG_KEY_0": "protocol.file.allow", "GIT_CONFIG_VALUE_0": "always",
            "GIT_CONFIG_KEY_1": f"url.{(self.root / 'app').as_uri()}.insteadOf",
            "GIT_CONFIG_VALUE_1": "https://gitcode.com/cann/cannbot.git",
        }

    def git(self, root, *args):
        return subprocess.run(
            ["git", "-C", str(root), *args], env=self.env, check=True,
            capture_output=True, text=True,
        ).stdout.strip()

    def write(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Fixture\n", encoding="utf-8")

    def commit(self, root):
        self.git(root, "add", ".")
        self.git(root, "commit", "-m", "Fixture")
        return self.git(root, "rev-parse", "HEAD")

    def install(self, *args):
        result = subprocess.run(
            [sys.executable, "-B", str(REPO / "install_codex.py"), "--task-dir",
             str(self.task), "--apply", *map(str, args)],
            env=self.env, capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.task / ".workflow-deps").exists())
        manifest = self.task / ".agents/ascend-op-workflow-install.json"
        return json.loads(manifest.read_text(encoding="utf-8"))

    def resolve(self, *args):
        helper = self.task / ".agents/skills/ascend-op-workflow/scripts/cannbot/resolve_source.py"
        return subprocess.run(
            [sys.executable, "-B", str(helper), "--task-dir",
             str(self.task), *map(str, args)],
            env=self.env, capture_output=True, text=True, encoding="utf-8",
        )

    def test_default_uses_application_gitlink_and_keeps_it_on_resume(self):
        self.assertIsNone(self.install()["cannbot_root"])
        skills = self.root / "skills"
        skills.mkdir()
        self.git(skills, "init", "-b", "master")
        for name in (*prepare.DEFAULT_SKILLS, "ops-evaluation"):
            self.write(skills / f"community/ops/ascendc-{name}/SKILL.md")
        skills_commit = self.commit(skills)

        app = self.root / "app"
        app.mkdir()
        self.git(app, "init", "-b", "master")
        self.write(app / "plugins-official/ops-direct-invoke/skills/ops-direct-invoke/SKILL.md")
        self.write(app / "plugins-community/ascendc-ops-perf-evolution/AGENTS.md")
        self.git(app, "submodule", "add", "--", skills.as_uri(), "vendor/cannbot-skills")
        app_commit = self.commit(app)
        self.write(skills / "NEW")
        self.commit(skills)

        first = self.resolve()
        self.assertEqual(first.returncode, 0, first.stderr)
        source = json.loads(first.stdout)
        self.assertEqual(source["application_commit"], app_commit)
        self.assertEqual(source["skills_commit"], skills_commit)
        self.assertEqual(source["default_branch"], "master")
        self.assertEqual(source["layout"], "application")

        self.write(app / "NEW")
        self.commit(app)
        resumed = self.resolve()
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        self.assertEqual(json.loads(resumed.stdout), source)

        lane = self.task / "lane"
        resource = prepare.prepare(lane, source["skills_root"], ["ops-evaluation"])
        self.assertEqual(Path(resource["environment"]["CANNBOT_WM_SCRIPTS"]),
                         lane / ".claude/skills/ascendc-evolution-world-model/scripts")
        self.assertTrue((lane / ".claude/skills/ascendc-ops-evaluation/SKILL.md").is_file())

    def test_explicit_legacy_source_works_offline(self):
        legacy = self.root / "legacy"
        self.write(legacy / "plugins-official/ops-direct-invoke/AGENTS.md")
        self.write(legacy / "plugins-community/ops-perf-evolution/AGENTS.md")

        self.install()
        first = self.resolve("--cannbot-root", legacy)
        self.assertEqual(first.returncode, 0, first.stderr)
        record = json.loads(first.stdout)
        self.assertEqual(record["layout"], "legacy")
        self.assertEqual(Path(record["source_root"]), legacy)
        self.assertFalse((self.task / ".workflow-deps/cannbot").exists())
        self.assertEqual(json.loads(self.resolve().stdout), record)

        other = self.root / "other"
        other.mkdir()
        rejected = self.resolve("--cannbot-root", other)
        self.assertIn("already uses CANNBot", rejected.stderr)

    def test_installer_records_application_path_without_staging_dependencies(self):
        app = self.root / "app"
        self.write(app / "plugins-official/ops-direct-invoke/skills/ops-direct-invoke/SKILL.md")
        manifest = self.install("--cannbot-root", app)
        self.assertEqual(Path(manifest["cannbot_root"]), app)
        result = self.resolve()
        self.assertIn("Initialize the CANNBot skills submodule", result.stderr)
        self.assertFalse((self.task / ".workflow-deps/cannbot").exists())
