"""Mock-only checks for the Linux launcher; no Claude process is started."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "launch-claude.sh"
BASH = shutil.which("bash") or (r"C:\Program Files\Git\bin\bash.exe" if os.name == "nt" else None)


@unittest.skipUnless(BASH and Path(BASH).is_file(), "Bash is unavailable")
class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.task = self.root / "task with spaces"
        (self.task / ".claude").mkdir(parents=True)
        (self.task / ".claude/workflow-bootstrap-manifest.json").write_text("{}", encoding="utf-8")
        (self.task / "TASK.md").write_text("# Test task\n", encoding="utf-8")
        mock_bin = self.root / "bin"
        mock_bin.mkdir()
        mock_claude = mock_bin / "claude"
        mock_claude.write_text(
            '#!/usr/bin/env bash\n'
            'printf "cwd=%s\\n" "$PWD" > "$CAPTURE"\n'
            'printf "sandbox=%s\\n" "$IS_SANDBOX" >> "$CAPTURE"\n'
            'printf "arg=%s\\n" "$@" >> "$CAPTURE"\n'
            'exit "${MOCK_CLAUDE_EXIT:-0}"\n', encoding="utf-8")
        mock_claude.chmod(0o755)
        self.capture = self.root / "capture.txt"
        self.env = os.environ.copy()
        self.env["PATH"] = str(mock_bin) + os.pathsep + self.env.get("PATH", "")
        self.env["CAPTURE"] = str(self.capture)

    def run_launcher(self, *args):
        return subprocess.run([BASH, str(SCRIPT), "--model", "task-model", "--effort", "medium", *args], env=self.env,
                              text=True, capture_output=True, check=False)

    def test_new_task_uses_sandbox_and_no_resume(self):
        result = self.run_launcher("--task-dir", str(self.task))
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = self.capture.read_text(encoding="utf-8").splitlines()
        self.assertIn("sandbox=1", lines)
        self.assertIn("arg=--dangerously-skip-permissions", lines)
        self.assertNotIn("arg=-c", lines)
        self.assertTrue(any(line.startswith("arg=Read TASK.md") for line in lines))

    def test_resume_is_explicit(self):
        result = self.run_launcher("--task-dir", str(self.task), "--resume", "exact-session", "--agent", "lingxi-evo")
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = self.capture.read_text(encoding="utf-8").splitlines()
        self.assertNotIn("arg=-c", lines)
        for item in ("--resume", "exact-session", "--model", "task-model", "--effort", "medium", "--agent", "lingxi-evo"):
            self.assertIn(f"arg={item}", lines)

    def test_resume_without_session_does_not_start_claude(self):
        result = self.run_launcher("--task-dir", str(self.task), "--resume")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.capture.exists())

    def test_executor_exit_status_propagates(self):
        self.env["MOCK_CLAUDE_EXIT"] = "17"
        self.assertEqual(self.run_launcher("--task-dir", str(self.task)).returncode, 17)

    def test_missing_manifest_blocks_launch(self):
        (self.task / ".claude/workflow-bootstrap-manifest.json").unlink()
        result = self.run_launcher("--task-dir", str(self.task))
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.capture.exists())

    def test_task_file_cannot_escape_task(self):
        result = self.run_launcher("--task-dir", str(self.task), "--task-file", "../outside.md")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.capture.exists())


if __name__ == "__main__":
    unittest.main()
