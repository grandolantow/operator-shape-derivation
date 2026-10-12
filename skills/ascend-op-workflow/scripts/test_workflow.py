"""Filesystem-only tests for workflow archive and evidence gates."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import workflow


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.original = self.make_file("original/kernel.py", "original")
        self.generated = self.make_file("generated/kernel.py", "generated")
        self.optimized = self.make_file("optimized/kernel.py", "optimized")
        self.skill = self.make_file("skill/SKILL.md", "# entry")
        self.log = self.make_file("logs/profile.json", '{"device":"NPU"}')
        self.case_manifest = self.make_file("cases.json", '{"case_ids":["case-a","case-b"]}')
        self.run = self.root / "run"

    def make_file(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data, encoding="utf-8")
        return path

    def invoke(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = workflow.main(list(args))
        return code, json.loads(out.getvalue()) if out.getvalue() else None, err.getvalue()

    def initialize(self, mode, input_kind="torch"):
        code, result, error = self.invoke(
            "init", "--run", str(self.run), "--name", "case", "--input-kind", input_kind,
            "--mode", mode, "--input", str(self.original),
            "--case-manifest", str(self.case_manifest),
        )
        self.assertEqual(code, 0, error)
        return result

    def freeze(self, path):
        code, result, error = self.invoke("freeze", "--run", str(self.run), "--package", str(path))
        self.assertEqual(code, 0, error)
        return result["package_id"]

    def evidence(self, baseline, candidate, b, c, **changes):
        data = {
            "provenance": "measured",
            "measurement": {"metric": "device_kernel_duration", "unit": "us", "protocol_id": "protocol-1", "paired_run_id": "pair-1", "device": "Ascend950"},
            "baseline_package": baseline,
            "candidate_package": candidate,
            "case_ids": ["case-a", "case-b"],
            "baseline_us": {"case-a": b, "case-b": b},
            "candidate_us": {"case-a": c, "case-b": c},
            "correctness": {"full": True, "passed": True, "case_ids": ["case-a", "case-b"]},
            "artifacts": [str(self.log)],
        }
        data.update(changes)
        return self.make_file(f"evidence/{candidate}.json", json.dumps(data))

    def prepare(self, stage, candidate=None, reuse=None):
        args = ["prepare", "--run", str(self.run), "--stage", stage, "--skill", str(self.skill)]
        if candidate:
            args.extend(["--candidate", candidate])
        if reuse:
            args.extend(["--reuse-evidence", str(reuse)])
        code, data, error = self.invoke(*args)
        self.assertEqual(code, 0, error)
        return data["preparation_id"]

    def result(self, stage, preparation, candidate, evidence=None):
        args = ["result", "--run", str(self.run), "--stage", stage,
                "--preparation", preparation, "--candidate", candidate,
                "--skill", str(self.skill)]
        if evidence:
            args.extend(["--evidence", str(evidence)])
        return self.invoke(*args)

    def test_rehearsal_handoff_has_null_measurements_and_real_package_lineage(self):
        self.initialize("rehearsal")
        generation_preparation = self.prepare("generation")
        generated = self.freeze(self.generated)
        code, result, error = self.result("generation", generation_preparation, generated)
        self.assertEqual(code, 0, error)
        self.assertEqual(result["status"], "REHEARSAL")
        optimized = self.freeze(self.optimized)
        optimization_preparation = self.prepare("optimization", generated)
        preparation_record = json.loads(
            (self.run / "preparations" / optimization_preparation / "prepare.json").read_text(encoding="utf-8")
        )
        self.assertEqual(preparation_record["route"], "rehearsal-generated")
        code, result, error = self.result("optimization", optimization_preparation, optimized)
        self.assertEqual(code, 0, error)
        handoff = json.loads(Path(result["path"]).read_text(encoding="utf-8"))
        self.assertEqual(handoff["baseline_package"], generated)
        self.assertIsNone(handoff["correctness"])
        self.assertIsNone(handoff["speedup_geomean"])
        self.assertEqual(handoff["target_speedup"], 1.5)
        self.assertEqual(handoff["optimization_plan"], {"rounds": 5, "candidates_per_round": 5})
        self.assertEqual(self.invoke("verify", "--run", str(self.run))[0], 0)

    def test_production_gates_and_distinct_denominators(self):
        self.initialize("production")
        generation_preparation = self.prepare("generation")
        generated = self.freeze(self.generated)
        evidence = self.evidence("original", generated, 100, 90)
        code, result, error = self.result("generation", generation_preparation, generated, evidence)
        self.assertEqual(code, 0, error)
        self.assertEqual(result["status"], "TARGET_UNMET")
        self.assertAlmostEqual(result["speedup_geomean"], 100 / 90)
        self.assertEqual(result["target_speedup"], 1.2)
        optimized = self.freeze(self.optimized)
        optimization_preparation = self.prepare("optimization", generated)
        evidence = self.evidence(generated, optimized, 90, 50)
        code, result, error = self.result("optimization", optimization_preparation, optimized, evidence)
        self.assertEqual(code, 0, error)
        self.assertEqual(result["status"], "TARGET_MET")
        self.assertAlmostEqual(result["speedup_geomean"], 1.8)
        self.assertEqual(result["target_speedup"], 1.5)

    def test_production_rejects_synthetic_incomplete_and_missing_measurement(self):
        self.initialize("production")
        generation_preparation = self.prepare("generation")
        generated = self.freeze(self.generated)
        for change in (
            {"provenance": "synthetic"},
            {"correctness": {"full": False, "passed": True, "case_ids": ["case-a", "case-b"]}},
            {"candidate_us": {"case-a": 80}},
            {"measurement": {"metric": "latency", "unit": "ms"}},
            {"artifacts": [str(self.root / "absent.json")]},
        ):
            evidence = self.evidence("original", generated, 100, 80, **change)
            code, _, _ = self.result("generation", generation_preparation, generated, evidence)
            self.assertEqual(code, 2)

    def test_tamper_rejected_before_more_work(self):
        self.initialize("rehearsal")
        generation_preparation = self.prepare("generation")
        generated = self.freeze(self.generated)
        config = json.loads((self.run / "run.json").read_text(encoding="utf-8"))
        archived = next(iter(config["packages"][generated]["files"]))
        (self.run / archived).write_text("tampered", encoding="utf-8")
        self.assertEqual(self.invoke("verify", "--run", str(self.run))[0], 2)
        self.assertEqual(self.result("generation", generation_preparation, generated)[0], 2)

    def test_init_never_overwrites_prior_history(self):
        self.initialize("rehearsal")
        before = (self.run / "run.json").read_bytes()
        code, _, _ = self.invoke("init", "--run", str(self.run), "--name", "another", "--input-kind", "torch", "--mode", "production", "--input", str(self.original))
        self.assertEqual(code, 2)
        self.assertEqual((self.run / "run.json").read_bytes(), before)

    def test_frozen_full_case_set_rejects_self_reported_subset(self):
        self.initialize("production")
        preparation = self.prepare("generation")
        generated = self.freeze(self.generated)
        evidence = self.evidence(
            "original", generated, 100, 70,
            case_ids=["case-a"], baseline_us={"case-a": 100},
            candidate_us={"case-a": 70},
            correctness={"full": True, "passed": True, "case_ids": ["case-a"]},
        )
        self.assertEqual(self.result("generation", preparation, generated, evidence)[0], 2)

    def test_reuse_ascendc_and_fixed_optimization_baseline(self):
        self.initialize("production", "ascendc")
        reuse = self.make_file("reuse.json", json.dumps({
            "provenance": "validated", "candidate_package": "original",
            "case_ids": ["case-a", "case-b"],
            "correctness": {"full": True, "passed": True, "case_ids": ["case-a", "case-b"]},
            "artifacts": [str(self.log)],
        }))
        self.prepare("optimization", "original", reuse)
        generated = self.freeze(self.generated)
        code, _, _ = self.invoke("prepare", "--run", str(self.run), "--stage", "optimization", "--candidate", generated, "--skill", str(self.skill), "--reuse-evidence", str(reuse))
        self.assertEqual(code, 2)

    def test_work_package_allowed_and_archive_ancestor_rejected(self):
        self.initialize("rehearsal")
        working = self.make_file("run/work/generated.py", "new")
        self.freeze(working)
        code, _, _ = self.invoke("freeze", "--run", str(self.run), "--package", str(self.root))
        self.assertEqual(code, 2)

    def test_rehearsal_mode_cannot_be_promoted_by_editing_run_json(self):
        self.initialize("rehearsal")
        config_path = self.run / "run.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["mode"] = "production"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        self.assertEqual(self.invoke("verify", "--run", str(self.run))[0], 2)


if __name__ == "__main__":
    unittest.main()
