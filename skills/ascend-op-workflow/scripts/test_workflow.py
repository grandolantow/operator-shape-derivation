"""Filesystem-only tests for workflow archive and evidence gates."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
        self.default_ids = ["case-a", "case-b"] + [f"case-{i}" for i in range(8)]
        manifest = {"case_ids": self.default_ids, "performance_case_ids": self.default_ids,
            "performance_selection": {"policy": "fixed10-v1", "ultra_large_case_ids": [],
                "classification": {"definition": "unit cases are small",
                    "cases": {i: {"ultra_large": False} for i in self.default_ids}}}}
        self.case_manifest = self.make_file("cases.json", json.dumps(manifest))
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
            "--case-manifest", str(self.case_manifest), "--stage-scope", "full",
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
            "case_ids": self.default_ids, "performance_case_ids": self.default_ids,
            "baseline_us": {i: b for i in self.default_ids},
            "candidate_us": {i: c for i in self.default_ids},
            "correctness": {"full": True, "passed": True, "case_ids": self.default_ids},
            "artifacts": [str(self.log)],
        }
        data.update(changes)
        return self.make_file(f"evidence/{candidate}.json", json.dumps(data))

    def prepare(self, stage, candidate=None, reuse=None):
        args = ["prepare", "--run", str(self.run), "--stage", stage, "--skill", str(self.skill)]
        if stage == "optimization":
            args.extend(["--round", "1"])
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

    def link(self, preparation, job="tool-job", *extra):
        return self.invoke("link", "--run", str(self.run), "--preparation", preparation,
                           "--job-id", job, "--endpoint", "test-endpoint", "--container", "test-container", *extra)

    def test_codex_execution_links_follow_generation_to_fixed_g_optimization(self):
        self.initialize("production")
        gen = self.prepare("generation")
        index_before = (self.run / "run.json").read_bytes()
        code, links, error = self.link(gen, "gen-job", "--model", "task-model", "--effort", "medium")
        self.assertEqual(code, 0, error)
        self.assertEqual(links["executions"][0]["executor"], "codex")
        self.assertIsNone(links["executions"][0]["claude_session_id"])
        self.assertEqual((self.run / "run.json").read_bytes(), index_before)
        g = self.freeze(self.generated)
        code, result, error = self.result("generation", gen, g, self.evidence("original", g, 100, 90))
        self.assertEqual(code, 0, error)
        self.assertEqual(self.link(gen, "gen-job", "--result", result["result_id"])[0], 0)
        opt = self.prepare("optimization", g)
        evo = self.root / "evolution"
        evo.mkdir()
        self.assertEqual(self.link(opt, "opt-job", "--evo-dir", str(evo))[0], 0)
        o = self.freeze(self.optimized)
        code, result, error = self.result("optimization", opt, o, self.evidence(g, o, 90, 70))
        self.assertEqual(code, 0, error)
        self.assertEqual(result["status"], "TARGET_UNMET")
        for _ in range(2):
            code, links, error = self.link(opt, "opt-job", "--result", result["result_id"], "--artifact", str(self.log))
            self.assertEqual(code, 0, error)
        self.assertEqual(len(links["executions"]), 2)
        self.assertEqual(links["executions"][1]["artifacts"], [str(self.log.resolve())])
        self.assertEqual(self.invoke("verify", "--run", str(self.run))[0], 0)

    def test_links_reject_cross_preparation_result_and_job_rebinding_without_writes(self):
        self.initialize("rehearsal")
        gen = self.prepare("generation")
        other = self.prepare("generation")
        g = self.freeze(self.generated)
        _, result, _ = self.result("generation", gen, g)
        self.assertEqual(self.link(gen)[0], 0)
        path = self.run / "execution-links.json"
        before = path.read_bytes()
        self.assertEqual(self.link(other, "other-job", "--result", result["result_id"])[0], 2)
        self.assertEqual(self.link(other)[0], 2)
        self.assertEqual(path.read_bytes(), before)

    def test_show_and_link_skip_hashing_but_final_verify_still_detects_changed_evidence(self):
        self.initialize("rehearsal")
        gen = self.prepare("generation")
        with patch.object(workflow, "digest", side_effect=AssertionError("metadata must not hash")):
            self.assertEqual(self.link(gen)[0], 0)
            self.assertEqual(self.invoke("show", "--run", str(self.run))[0], 0)
        archived = next((self.run / "packages/original/source").iterdir())
        archived.write_text("changed", encoding="utf-8")
        self.assertEqual(self.invoke("show", "--run", str(self.run))[0], 0)
        self.assertEqual(self.invoke("verify", "--run", str(self.run))[0], 2)

    def test_claude_session_is_optional_and_bound_only_to_selected_executor(self):
        self.initialize("rehearsal")
        gen = self.prepare("generation")
        self.assertEqual(self.link(gen, "claude-job", "--claude-session", "session-a")[0], 2)
        code, links, error = self.link(gen, "claude-job", "--executor", "claude", "--claude-session", "session-a")
        self.assertEqual(code, 0, error)
        self.assertEqual(links["executions"][0]["claude_session_id"], "session-a")
        self.assertEqual(self.link(gen, "claude-job", "--claude-session", "session-b")[0], 2)

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
        # A correct G slower than R must remain usable as the fixed optimization baseline.
        evidence = self.evidence("original", generated, 100, 200)
        code, result, error = self.result("generation", generation_preparation, generated, evidence)
        self.assertEqual(code, 0, error)
        self.assertEqual(result["status"], "TARGET_UNMET")
        self.assertAlmostEqual(result["speedup_geomean"], 0.5)
        self.assertEqual(result["target_speedup"], 1.2)
        optimized = self.freeze(self.optimized)
        optimization_preparation = self.prepare("optimization", generated)
        evidence = self.evidence(generated, optimized, 200, 100)
        code, result, error = self.result("optimization", optimization_preparation, optimized, evidence)
        self.assertEqual(code, 0, error)
        self.assertEqual(result["status"], "TARGET_MET")
        self.assertAlmostEqual(result["speedup_geomean"], 2.0)
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
            "case_ids": self.default_ids,
            "correctness": {"full": True, "passed": True, "case_ids": self.default_ids},
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

    def performance_manifest(self):
        ids = [str(i) for i in range(29)]
        data = {"case_ids": ids, "performance_case_ids": ids[:10],
                "performance_selection": {"policy": "fixed10-v1", "ultra_large_case_ids": ids[:3],
                    "classification": {"definition": "unit fixture: IDs 0..2 are large",
                        "cases": {i: {"ultra_large": int(i) < 3} for i in ids}}}}
        return data

    def initialize_selected(self, manifest=None, *extra):
        data = self.performance_manifest() if manifest is None else manifest
        path = self.make_file("selected-cases.json", json.dumps(data))
        return self.invoke("init", "--run", str(self.run), "--name", "selected",
                           "--input-kind", "torch", "--mode", "production",
                           "--input", str(self.original), "--case-manifest", str(path), *extra)

    def selected_evidence(self, candidate, **changes):
        data = self.performance_manifest()
        fields = {"case_ids": data["case_ids"], "performance_case_ids": data["performance_case_ids"],
                  "correctness": {"full": True, "passed": True, "case_ids": data["case_ids"]},
                  "baseline_us": {i: 100 for i in data["performance_case_ids"]},
                  "candidate_us": {i: 50 for i in data["performance_case_ids"]}}
        fields.update(changes)
        return self.evidence("original", candidate, 100, 50, **fields)

    def auto_acceptance(self, candidate_us=50, *extra):
        self.assertEqual(self.initialize_selected(None, *extra)[0], 0)
        candidate = self.freeze(self.generated)
        prep = self.prepare("generation")
        evidence = self.selected_evidence(candidate, candidate_us={str(i): candidate_us for i in range(10)})
        code, result, error = self.result("generation", prep, candidate, evidence)
        self.assertEqual(code, 0, error)
        return candidate, result

    def auto_prepare(self, candidate, *extra):
        return self.invoke("prepare", "--run", str(self.run), "--stage", "optimization",
                           "--candidate", candidate, "--skill", str(self.skill), "--round", "1", *extra)

    def test_auto_default_requires_fixed10_and_freezes_controls(self):
        self.case_manifest = self.make_file("legacy-cases.json", '{"case_ids":["case-a","case-b"]}')
        code, _, error = self.invoke("init", "--run", str(self.run), "--name", "auto",
            "--input-kind", "torch", "--mode", "production", "--input", str(self.original),
            "--case-manifest", str(self.case_manifest))
        self.assertEqual(code, 2)
        self.assertIn("fixed10", error)
        self.assertFalse(self.run.exists())
        self.assertEqual(self.initialize_selected()[0], 0)
        config = workflow.load_run(self.run)
        self.assertEqual(config["stage_scope"], "auto")
        self.assertTrue(config["round_review_required"])
        self.assertEqual(config["optimization_plan"], {"rounds": 5, "candidates_per_round": 5})
        for field, value in [("stage_scope", "full"), ("round_review_required", False)]:
            changed = dict(config, **{field: value})
            (self.run / "run.json").write_text(json.dumps(changed))
            self.assertEqual(self.invoke("verify", "--run", str(self.run))[0], 2)
        (self.run / "run.json").write_text(json.dumps(config))

    def test_all_new_production_scopes_require_fixed10_and_reviews(self):
        invalid = self.make_file("missing-perf.json", '{"case_ids":["a"]}')
        for scope in ("auto", "full", "generation_only"):
            with self.subTest(scope=scope):
                self.run = self.root / scope
                self.assertEqual(self.invoke("init", "--run", str(self.run), "--name", "new",
                    "--input-kind", "torch", "--mode", "production", "--input", str(self.original),
                    "--case-manifest", str(invalid), "--stage-scope", scope)[0], 2)
                self.assertFalse(self.run.exists())
                self.assertEqual(self.initialize_selected(None, "--stage-scope", scope)[0], 0)
                config = workflow.load_run(self.run)
                self.assertTrue(config["round_review_required"])
                self.assertEqual(config["stage_scope"], scope)

    def test_decision_uses_frozen_preparation_and_rejects_inconsistent_binding(self):
        candidate, result = self.auto_acceptance()
        config = workflow.read_run(self.run)
        handoff = json.loads(Path(result["path"]).read_text())
        prep_id = handoff["preparation_id"]
        config["preparations"][prep_id]["stage"] = "optimization"
        (self.run / "run.json").write_text(json.dumps(config))
        code, decision, error = self.invoke("decision", "--run", str(self.run), "--candidate", candidate)
        self.assertEqual(code, 0, error)
        self.assertEqual(decision["next_action"], "deliver_G")
        # Even a self-consistent replacement checksum cannot bypass semantic binding.
        handoff["baseline_package"] = candidate
        Path(result["path"]).write_text(json.dumps(handoff))
        relative = f"handoffs/{result['result_id']}/handoff.json"
        config["handoffs"][result["result_id"]]["files"][relative] = workflow.digest(Path(result["path"]))
        (self.run / "run.json").write_text(json.dumps(config))
        self.assertEqual(self.invoke("decision", "--run", str(self.run), "--candidate", candidate)[0], 2)

    def test_auto_met_delivers_and_unchecked_status_cannot_trigger_optimization(self):
        candidate, result = self.auto_acceptance()
        self.assertEqual(result["decision"]["next_action"], "deliver_G")
        self.assertEqual(result["decision"]["correctness_status"], "FULL_PASS")
        self.assertEqual(self.auto_prepare(candidate)[0], 2)
        config = workflow.read_run(self.run)
        config["handoffs"][result["result_id"]]["status"] = "TARGET_UNMET"
        (self.run / "run.json").write_text(json.dumps(config))
        code, decision, error = self.invoke("decision", "--run", str(self.run), "--candidate", candidate)
        self.assertEqual(code, 0, error)
        self.assertEqual(decision["next_action"], "deliver_G")
        self.assertEqual(self.auto_prepare(candidate)[0], 2)

    def test_auto_unmet_dispatch_and_frozen_g(self):
        candidate, result = self.auto_acceptance(200)
        self.assertEqual(result["decision"]["performance_status"], "TARGET_UNMET")
        self.assertEqual(result["decision"]["next_action"], "optimize")
        self.assertEqual(self.auto_prepare(candidate)[0], 0)
        other = self.freeze(self.optimized)
        self.assertEqual(self.auto_prepare(other)[0], 2)
        # Mutable index fields cannot replace the baseline frozen in prepare.json.
        config = workflow.read_run(self.run)
        for item in config["preparations"].values():
            if item["stage"] == "optimization": item["baseline_package"] = other
        (self.run / "run.json").write_text(json.dumps(config))
        self.assertEqual(self.auto_prepare(other)[0], 2)

    def test_auto_missing_invalid_and_conflicting_acceptance_never_dispatch(self):
        self.assertEqual(self.initialize_selected()[0], 0)
        candidate = self.freeze(self.generated)
        self.assertEqual(self.auto_prepare(candidate)[0], 2)
        code, decision, _ = self.invoke("decision", "--run", str(self.run), "--candidate", candidate)
        self.assertEqual(code, 0)
        self.assertEqual(decision["next_action"], "acceptance_required")
        prep = self.prepare("generation")
        self.assertEqual(self.result("generation", prep, candidate,
            self.selected_evidence(candidate, candidate_us={str(i): 0 for i in range(10)}))[0], 2)
        self.assertEqual(self.auto_prepare(candidate)[0], 2)
        self.assertEqual(self.result("generation", prep, candidate, self.selected_evidence(candidate))[0], 0)
        evidence = self.selected_evidence(candidate, candidate_us={str(i): 200 for i in range(10)})
        code, result, error = self.result("generation", prep, candidate, evidence)
        self.assertEqual(code, 0, error)
        self.assertEqual(result["decision"]["performance_status"], "CONFLICTING")
        self.assertEqual(self.auto_prepare(candidate)[0], 2)
        archived = Path(result["path"])
        archived.write_text("{}")
        self.assertEqual(self.invoke("decision", "--run", str(self.run), "--candidate", candidate)[0], 2)

    def test_changed_g_result_fails_without_changing_archive(self):
        candidate, _ = self.auto_acceptance(200)
        self.assertEqual(self.auto_prepare(candidate)[0], 0)
        other = self.freeze(self.optimized)
        prep = self.prepare("generation")
        evidence = self.selected_evidence(other)
        before = {p.relative_to(self.run): p.read_bytes() for p in self.run.rglob("*") if p.is_file()}
        self.assertEqual(self.result("generation", prep, other, evidence)[0], 2)
        self.assertEqual(before, {p.relative_to(self.run): p.read_bytes()
                                 for p in self.run.rglob("*") if p.is_file()})

    def test_auto_ascendc_reuse_requires_measured_acceptance(self):
        self.assertEqual(self.initialize_selected()[0], 0)
        # Set up a separate AscendC run with the identical frozen performance protocol.
        self.run = self.root / "ascendc-run"
        manifest = self.make_file("reuse-cases.json", json.dumps(self.performance_manifest()))
        self.assertEqual(self.invoke("init", "--run", str(self.run), "--name", "reuse",
            "--input-kind", "ascendc", "--mode", "production", "--input", str(self.original),
            "--case-manifest", str(manifest))[0], 0)
        candidate = self.freeze(self.generated)
        validation = self.selected_evidence(candidate, provenance="validated")
        self.assertEqual(self.auto_prepare(candidate, "--reuse-evidence", str(validation))[0], 2)
        prep = self.prepare("generation")
        evidence = self.selected_evidence(candidate, candidate_us={str(i): 200 for i in range(10)})
        self.assertEqual(self.result("generation", prep, candidate, evidence)[0], 0)
        self.assertEqual(self.auto_prepare(candidate)[0], 0)

    def test_explicit_full_met_still_authorizes_optimization(self):
        candidate, result = self.auto_acceptance(50, "--stage-scope", "full")
        self.assertEqual(result["decision"]["next_action"], "optimize")
        self.assertEqual(self.auto_prepare(candidate)[0], 0)

    def test_legacy_absent_scope_keeps_full_route(self):
        self.initialize("production")
        # Reconstruct a historical archive identity lacking the new controls.
        config = workflow.read_run(self.run)
        identity_path = self.run / "inputs/identity.json"
        identity = json.loads(identity_path.read_text())
        for field in ("stage_scope", "performance_case_ids", "performance_selection", "round_review_required"):
            config.pop(field, None)
            identity.pop(field, None)
        identity_path.write_text(json.dumps(identity))
        config["files"]["inputs/identity.json"] = workflow.digest(identity_path)
        (self.run / "run.json").write_text(json.dumps(config))
        self.assertNotIn("stage_scope", workflow.load_run(self.run))
        candidate = self.freeze(self.generated)
        prep = self.prepare("generation")
        code, result, error = self.result("generation", prep, candidate, self.evidence("original", candidate, 100, 50))
        self.assertEqual(code, 0, error)
        self.assertEqual(result["decision"]["stage_scope"], "full")
        self.assertEqual(result["decision"]["next_action"], "optimize")
        self.prepare("optimization", candidate)

    def test_auto_respects_configured_generation_target(self):
        candidate, result = self.auto_acceptance(50, "--generation-target", "3")
        self.assertEqual(result["decision"]["target_speedup"], 3)
        self.assertEqual(result["decision"]["next_action"], "optimize")
        self.assertEqual(self.auto_prepare(candidate)[0], 0)

    def test_auto_rehearsal_keeps_unmeasured_preparation_path(self):
        self.assertEqual(self.invoke("init", "--run", str(self.run), "--name", "demo",
            "--input-kind", "torch", "--mode", "rehearsal", "--input", str(self.original))[0], 0)
        candidate = self.freeze(self.generated)
        self.assertEqual(self.auto_prepare(candidate)[0], 0)
        code, decision, _ = self.invoke("decision", "--run", str(self.run), "--candidate", candidate)
        self.assertEqual(code, 0)
        self.assertEqual(decision["performance_status"], "UNMEASURED")
        self.assertEqual(decision["next_action"], "acceptance_required")

    def test_full29_correctness_and_separate10_performance(self):
        self.assertEqual(self.initialize_selected()[0], 0)
        prep = self.prepare("generation")
        candidate = self.freeze(self.generated)
        code, result, error = self.result("generation", prep, candidate, self.selected_evidence(candidate))
        self.assertEqual(code, 0, error)
        self.assertAlmostEqual(result["speedup_geomean"], 2)
        handoff = json.loads(Path(result["path"]).read_text())
        self.assertEqual(len(handoff["case_ids"]) if "case_ids" in handoff else len(handoff["correctness"]["case_ids"]), 29)
        self.assertEqual(len(handoff["performance_case_ids"]), 10)

    def test_performance_selection_rejects_wrong_count_duplicate_outside_and_large_mismatch(self):
        for problem in ["count", "duplicate", "outside", "four_large", "hidden_large"]:
            with self.subTest(problem=problem):
                data = self.performance_manifest()
                if problem == "count": data["performance_case_ids"].pop()
                if problem == "duplicate": data["performance_case_ids"][-1] = "0"
                if problem == "outside": data["performance_case_ids"][-1] = "absent"
                if problem == "four_large":
                    data["performance_selection"]["ultra_large_case_ids"].append("3")
                    data["performance_selection"]["classification"]["cases"]["3"]["ultra_large"] = True
                if problem == "hidden_large": data["performance_selection"]["ultra_large_case_ids"].pop()
                self.assertEqual(self.initialize_selected(data)[0], 2)
                self.assertFalse(self.run.exists())

    def test_selected_perf_does_not_relax_correctness_or_allow_missing_timing(self):
        self.assertEqual(self.initialize_selected()[0], 0)
        prep = self.prepare("generation")
        candidate = self.freeze(self.generated)
        for changes in [
            {"correctness": {"full": True, "passed": True, "case_ids": [str(i) for i in range(28)]}},
            {"performance_case_ids": None},
            {"performance_case_ids": [str(i) for i in range(9)] + ["10"]},
            {"candidate_us": {str(i): 50 for i in range(9)}},
        ]:
            self.assertEqual(self.result("generation", prep, candidate, self.selected_evidence(candidate, **changes))[0], 2)

    def test_performance_identity_cannot_be_changed_in_place(self):
        self.assertEqual(self.initialize_selected()[0], 0)
        p = self.run / "run.json"
        config = json.loads(p.read_text())
        config["performance_case_ids"][-1] = "10"
        p.write_text(json.dumps(config))
        self.assertEqual(self.invoke("verify", "--run", str(self.run))[0], 2)

    def test_generation_only_rejects_optimization_and_round_start(self):
        self.assertEqual(self.initialize_selected(None, "--stage-scope", "generation_only")[0], 0)
        prep = self.prepare("generation")
        candidate = self.freeze(self.generated)
        self.assertEqual(self.result("generation", prep, candidate, self.selected_evidence(candidate))[0], 0)
        self.assertEqual(self.invoke("prepare", "--run", str(self.run), "--stage", "optimization",
                                     "--skill", str(self.skill), "--candidate", candidate)[0], 2)
        self.assertEqual(self.invoke("round-check", "--run", str(self.run), "--next-round", "1")[0], 2)

    def round_review(self, failed=False):
        candidates = []
        for i in range(5):
            candidates.append({"candidate_id": f"p{i}", "status": "build_failed" if failed else "evaluated",
                "artifacts": [str(self.log)], "analysis": {"status": "unknown",
                    "observations": "Observed timing, or retained build error", "explanation": "Cause not established",
                    "next_experiment": "Measure launch count and repeat isolated change",
                    "expected_observation": "Reduced launches with unchanged full correctness",
                    "slow_cases": [] if failed else [{"case_id": "0", "baseline_us": 100, "candidate_us": 120}]}})
        return {"round": 1, "candidates": candidates, "next_round_candidates": [
            {"hypothesis_id": f"h{i}", "mechanism_change": f"Independent mechanism {i}",
             "rationale": "Observed overhead", "falsifier": "No timing reduction under repeated sampling",
             "source_candidate_ids": [f"p{i}"], "expected_case_ids": ["0"]} for i in range(5)]}

    def test_next_round_requires_review_unknown_with_experiment_is_accepted(self):
        self.assertEqual(self.initialize_selected(None, "--require-round-reviews", "--optimization-seconds", "18000")[0], 0)
        self.assertEqual(self.invoke("round-check", "--run", str(self.run), "--next-round", "2")[0], 2)
        data = self.round_review()
        path = self.make_file("review.json", json.dumps(data))
        code, result, error = self.invoke("round-review", "--run", str(self.run), "--record", str(path))
        self.assertEqual(code, 0, error)
        self.assertEqual(self.invoke("round-check", "--run", str(self.run), "--next-round", "2")[0], 0)
        archived = next((Path(result["path"]) / "references").iterdir())
        archived.write_text("changed")
        self.assertEqual(self.invoke("verify", "--run", str(self.run))[0], 2)

    def test_review_rejects_unexplained_results_and_unlinked_combinations(self):
        self.assertEqual(self.initialize_selected(None, "--require-round-reviews")[0], 0)
        for problem in ["missing_candidate", "empty_experiment", "missing_slow_case", "unknown_parent"]:
            data = self.round_review()
            if problem == "missing_candidate": data["candidates"].pop()
            if problem == "empty_experiment": data["candidates"][0]["analysis"]["next_experiment"] = ""
            if problem == "missing_slow_case": data["candidates"][0]["analysis"]["slow_cases"] = []
            if problem == "unknown_parent": data["next_round_candidates"][0]["source_candidate_ids"] = ["other"]
            path = self.make_file("bad-review.json", json.dumps(data))
            self.assertEqual(self.invoke("round-review", "--run", str(self.run), "--record", str(path))[0], 2)

    def test_all_failed_round_can_be_analyzed_without_performance_files(self):
        self.assertEqual(self.initialize_selected(None, "--require-round-reviews")[0], 0)
        data = self.round_review(failed=True)
        data.update(next_round_candidates=[], stop_reason="Time budget exhausted")
        path = self.make_file("failed-review.json", json.dumps(data))
        self.assertEqual(self.invoke("round-review", "--run", str(self.run), "--record", str(path))[0], 0)
        self.assertEqual(self.invoke("round-check", "--run", str(self.run), "--next-round", "2")[0], 2)

    def test_terminal_review_cannot_be_bypassed_by_restarting_round_one(self):
        self.assertEqual(self.initialize_selected(None, "--require-round-reviews")[0], 0)
        data = self.round_review(failed=True)
        data.update(next_round_candidates=[], stop_reason="Time budget exhausted")
        path = self.make_file("stop-review.json", json.dumps(data))
        self.assertEqual(self.invoke("round-review", "--run", str(self.run), "--record", str(path))[0], 0)
        for number in (1, 2, 5):
            self.assertEqual(self.invoke("round-check", "--run", str(self.run), "--next-round", str(number))[0], 2)
        self.assertEqual(self.invoke("prepare", "--run", str(self.run), "--stage", "optimization",
                                     "--skill", str(self.skill), "--candidate", "original")[0], 2)
        # A correction to this review remains append-only and is allowed before later rounds.
        self.assertEqual(self.invoke("round-review", "--run", str(self.run), "--record", str(path))[0], 0)

    def test_completed_round_rejects_restart_but_allows_its_next_round(self):
        self.assertEqual(self.initialize_selected(None, "--require-round-reviews")[0], 0)
        path = self.make_file("review.json", json.dumps(self.round_review()))
        self.assertEqual(self.invoke("round-review", "--run", str(self.run), "--record", str(path))[0], 0)
        self.assertEqual(self.invoke("round-check", "--run", str(self.run), "--next-round", "1")[0], 2)
        self.assertEqual(self.invoke("round-check", "--run", str(self.run), "--next-round", "2")[0], 0)

    def test_round_review_index_drift_cannot_bypass_frozen_stop(self):
        self.assertEqual(self.initialize_selected()[0], 0)
        data = self.round_review(failed=True)
        data.update(next_round_candidates=[], stop_reason="Budget exhausted")
        path = self.make_file("review.json", json.dumps(data))
        self.assertEqual(self.invoke("round-review", "--run", str(self.run), "--record", str(path))[0], 0)
        original = workflow.read_run(self.run)
        for field, replacement in (("next_round_ready", True), ("round", 2), ("sequence", 99)):
            with self.subTest(field=field):
                config = json.loads(json.dumps(original))
                next(iter(config["round_reviews"].values()))[field] = replacement
                (self.run / "run.json").write_text(json.dumps(config))
                self.assertEqual(self.invoke("verify", "--run", str(self.run))[0], 2)
                self.assertEqual(self.invoke("round-check", "--run", str(self.run), "--next-round", "2")[0], 2)
                self.assertEqual(self.auto_prepare("original")[0], 2)

    def test_legacy_round_review_remains_readable_without_dispatch_permission(self):
        self.assertEqual(self.initialize_selected()[0], 0)
        path = self.make_file("review.json", json.dumps(self.round_review()))
        self.assertEqual(self.invoke("round-review", "--run", str(self.run), "--record", str(path))[0], 0)
        config = workflow.read_run(self.run)
        identifier, meta = next(iter(config["round_reviews"].items()))
        relative = f"round-reviews/{identifier}/review.json"
        del meta["files"][relative]
        (self.run / "run.json").write_text(json.dumps(config))
        self.assertEqual(self.invoke("verify", "--run", str(self.run))[0], 0)
        self.assertEqual(self.invoke("round-check", "--run", str(self.run), "--next-round", "2")[0], 2)


if __name__ == "__main__":
    unittest.main()
