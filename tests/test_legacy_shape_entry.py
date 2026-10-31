"""Legacy consumers must retain checker results and failure exit codes."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "scripts/check_execution_contract.py"
CANONICAL = ROOT / "skills/operator-shape-derivation/scripts/check_execution_contract.py"


class LegacyShapeTests(unittest.TestCase):
    def test_cli_results_and_exit_codes(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "contract.json"
            for status, value, expected in (("configured", 4, 0), ("unknown", None, 2)):
                source.write_text(json.dumps({"execution_contract": {
                    "quantities": {"M": {"value": value, "status": status,
                        "scope": "operator rows", "evidence": "test"}},
                    "required_for_export": ["M"], "decisions": []}}), encoding="utf-8")
                results = [subprocess.run([sys.executable, str(script), str(source)],
                           capture_output=True, text=True) for script in (LEGACY, CANONICAL)]
                self.assertEqual([r.returncode for r in results], [expected, expected])
                self.assertEqual(json.loads(results[0].stdout), json.loads(results[1].stdout))
            source.write_text("invalid json", encoding="utf-8")
            result = subprocess.run([sys.executable, str(LEGACY), str(source)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)["issues"][0]["code"], "input-error")

    def test_import_interface(self):
        reports = []
        for index, script in enumerate((LEGACY, CANONICAL)):
            spec = importlib.util.spec_from_file_location(f"checker_{index}", script)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            reports.append(module.validate_contract({}))
        self.assertEqual(reports[0], reports[1])


if __name__ == "__main__":
    unittest.main()
