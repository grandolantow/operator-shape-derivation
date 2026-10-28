# Workflow archive CLI

`workflow.py` uses only Python's standard library. It copies and hashes local files, checks the structure of supplied evidence, and writes reviewable stage records. It never compiles, runs kernels, measures an NPU, invokes another command, or treats a filename as proof of correctness.

## Commands

```text
python workflow.py init --run RUN --name NAME --input-kind ascendc|triton|torch --mode production|rehearsal --input PATH [--input PATH ...] [--case-manifest CASES.json] [--generation-target 1.2] [--optimization-target 1.5] [--rounds 5] [--variants 5]
python workflow.py freeze --run RUN --package PATH
python workflow.py prepare --run RUN --stage generation|optimization --skill SKILL.md [--candidate G_PACKAGE_ID] [--reuse-evidence REUSE.json]
python workflow.py result --run RUN --stage generation|optimization --preparation PREPARATION_ID --candidate PACKAGE_ID --skill SKILL.md [--evidence EVIDENCE.json]
python workflow.py inspect --run RUN
python workflow.py verify --run RUN
python workflow.py link --run RUN --preparation PREPARATION_ID --job-id JOB_ID --endpoint ALIAS --container CONTAINER [--executor codex|claude] [--model MODEL] [--effort EFFORT] [--claude-session SESSION_ID] [--evo-dir DIR] [--artifact PATH ...] [--result RESULT_ID]
python workflow.py show --run RUN
```

`init` creates a new run only; it never overwrites one. It freezes the original inputs as package `original`. Production requires `--case-manifest`, a JSON object with a nonempty, unique `case_ids` array. Targets and the optimization plan are frozen in `run.json`. `freeze` archives a generated or optimized source tree and returns its package ID. A source under `RUN/work` is allowed; a source containing `RUN` or inside the immutable `packages`, `preparations`, or `handoffs` archives is rejected.

`link` records actual tool receipts in `execution-links.json`; it never submits, resumes, polls or cancels work. New entries default to Codex and need no Claude session. Select `--executor claude` when supplying a Claude session. Repeating the same link adds references without duplicating jobs; established preparation/endpoint/container/session/evo/result identity cannot be replaced. A result must belong to the same preparation. Artifact paths must exist and may keep growing; final evidence is frozen by `result`, not `link`. Model/effort record observed choices when available. `show` reads these references, not live job state. Both commands read only metadata and skip archive hashing; `verify` remains the full integrity check. One parent coordinator writes links. See [MindIE integration](../references/mindie.md) for execution and recovery.

`prepare generation` needs only the frozen original input and a readable skill entry. `prepare optimization` needs a frozen G package. In production it requires a previous generation result for that G, or, for an existing AscendC input, `--reuse-evidence` validating the frozen G package. In rehearsal, a frozen synthetic G is enough. The first optimization preparation fixes G as the comparison denominator for that run; changing G requires a new run. Both preparation records carry the numeric target, while correctness and measured speedup remain null.

`result` requires its matching preparation ID and a frozen result package. Production additionally requires evidence. It computes the geometric mean of per-case `baseline_us / candidate_us` across exactly the frozen case manifest. Generation compares `original` to G against the generation target. Optimization compares the fixed G to O against the optimization target. A correct G below the generation target is recorded as `TARGET_UNMET` and can still be handed to optimization; it is never silently marked as meeting the target. Rehearsal results contain null correctness and speedup, with status `REHEARSAL`.

Production result evidence schema:

```json
{
  "provenance": "measured",
  "measurement": {
    "metric": "device_kernel_duration",
    "unit": "us",
    "protocol_id": "same-workload-and-timing-protocol",
    "paired_run_id": "baseline-candidate-pair-001",
    "device": "Ascend950"
  },
  "baseline_package": "original",
  "candidate_package": "package-ID-from-freeze",
  "case_ids": ["case-a", "case-b"],
  "baseline_us": {"case-a": 100.0, "case-b": 200.0},
  "candidate_us": {"case-a": 80.0, "case-b": 150.0},
  "correctness": {"full": true, "passed": true, "case_ids": ["case-a", "case-b"]},
  "artifacts": ["/path/to/raw-correctness-log", "/path/to/raw-profile"]
}
```

Production AscendC reuse evidence omits timing maps and uses `"provenance":"validated"`; it still supplies `candidate_package`, the exact frozen `case_ids`, passing full `correctness`, and existing `artifacts`. Artifact paths may be files or directories. The CLI copies their bytes alongside each preparation or result and hashes them. `verify` rejects missing or changed archived files and linked archive paths. Skill entries may be reached through an existing junction or symlink; the tool resolves them before read-only copying into the archive.

The `--skill` argument accepts the actual readable instruction entry file, including
`AGENTS.md` when a CANNBot plugin uses that as its coordinator entry. The generation
and evolution plugin roots in this distribution use `AGENTS.md`; do not invent a
root `SKILL.md` path. Individual installed skills still use `SKILL.md`.

**Evidence limit:** The CLI checks schema, case coverage, package lineage, positive timing values, and hashes of supplied files. It does not parse profiler logs or prove that the declared protocol, device, timings, and correctness verdict match the raw logs. The operator owner must inspect the actual archived logs, timing semantics, workload, and correctness report before accepting a production result.

## C/V serial projects

The [C/V branch](../references/cv-serial.md) uses the existing commands; there is no `cv-serial` CLI flag or automatic component dispatcher. Include the selection record, boundary contract, case mapping, both components, adapters and complete runner in the frozen project. Generation/optimization evidence and timing maps refer to full parent cases and the complete path. Component-only results are diagnostic artifacts, not parent acceptance evidence.

Before G is established, newly assembled C/V projects use generation acceptance even when both components were reused. Skipping generation applies to a validated existing complete AscendC project, subject to the reuse rules above. If G was already frozen, switching to C/V creates an optimization candidate O against that original G, even when a generation skill helps adapt its components; do not record it as a new generation baseline. The CLI cannot verify C/V semantics or the three correctness layers; the coordinating agent must inspect those raw records before recording the parent result.

Keep active parent/child state and consumed budget in the task's designated state file. Do not edit frozen run identity or fixed G. If an authorized change requires a new archive run, link it to the same parent task and predecessor, carrying forward the remaining budget. A route or ABI change alone does not reset the optimization denominator or create another 5 rounds.
