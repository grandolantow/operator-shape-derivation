# 完整执行协议

仅用于明确选择完整原生进化，或恢复已采用原生 state/anchor 的任务。新任务默认读 [轻量执行](cannbot-lightweight.md)，不预先执行下面整套初始化。完整模式同样使用 adapter 评分校验；原生代码保持只读。

## 路径与准备

先按[执行适配入口](cannbot-execution.md)解析当前环境的只读 CANNBot checkout 和本 workflow 的 scripts/cannbot（ADAPTER），按需运行资源准备；原任务已有布局则沿用。固定 WORKDIR、EVO_DIR、WM、EVAL、PROF 为实际任务/资源路径。lingxi 的 SCORE_BASE=pytorch，ops 的 SCORE_BASE=native；不引用本机私有安装包或 vendor 快照。

准备脚本只建立资源兼容布局，不会替你冻结用户基线或证明运行环境可用。基线先复制到 `EVO_DIR/baseline_source`，记录散列、源码版本及未提交差异。后续 `.json.bak` 全量恢复、build/ 清理和性能采集都指向该副本。源码副本中的全量模型、输入、容差与 call_spec 冻结后放入 `shared/`。并行构建还需独立环境/安装目录，因为 translator 的 `pip --force-reinstall` 会污染共享 Python 环境。

## 独立全量覆盖守卫

按[正式验收与全量覆盖](cannbot-execution.md#正式验收与全量覆盖)调用本 workflow 的 gate（显式传 --cannbot-root），核对真实 loader、完整清单、源码/日志及加载库身份。原世界模型按 JSON 行数推断的计数不能替代正式全量证明。direct-invoke/native-entry 使用其合同 verifier，不将 translator gate 宣称为通用验收。

## Codex 调度映射

由当前宿主的唯一协调者组织原生角色和真实工具；角色数量、候选宽度不等于必须同时新建相同数量 agent。模型、effort、并发、等待及取消服从当前项目/任务约定。明确源码归属和独立审查；取消 agent 后核实其真实 shell/NPU 作业已退出。

每个 partial 的 prompt 必含：node ID、round/lane、唯一写目录、父变体只读路径、冻结输入清单、模式/强制方向、策略兼容性、完整资源路径、评估协议、设备与独立环境、编译及局部修复上限、结果 JSON/日志路径、失败也必须写真实结果。使用源 `evolution-strategies/references/prompts/{lingxi,ops}-partial-prompt.md` 的完整语义；无需原样保留失效的 Claude 调用语法。

## 初始化、预约、反馈的准确顺序

1. 创建固定结果目录，写 anchor（新 run 一次）：

   ```bash
   python3 -B "$WM/session_anchor.py" write --op-name "$OP" --evo-dir "$EVO_DIR" --requested-rounds "$ROUNDS"
   ```

2. 复用身份一致、已经核查的正式基线精度与计时证据；缺失或失效时补验。生成 `baseline_evaluation.json`。lingxi 时间来源可用：

   ```bash
   bash "$PROF/msprof_profile_run.sh" --quick --quick-batch --output-dir="$EVO_DIR/baseline_source" --warm-up=3 --device="$NPU" --retry=2
   python3 -B "$WM/generate_baseline_eval.py" --perf-json "$EVO_DIR/baseline_source/performance.json" --baseline-path "$EVO_DIR/baseline_source" --output "$EVO_DIR/baseline_evaluation.json" --op-name "$OP" --timestamp "$STAMP"
   ```

   此计时结果不替代正式精度门禁，尤其不能把“有有效时间”解释为全量精度通过。ops 基线以正式 evaluator 的基线输出为准；依赖缺失时停在该分支并保留静态产物。

3. 读所选 checkout 的 `evolution-world-model/references/schema.md` 和 `operations.md`，根据真实基线与策略推理写 `world_model.json`（`decision_tree.nodes` 是按 ID 索引的字典）。root 节点为 `completed`，待测节点 `open/score:null`；填 kernel_summary、baseline_performance、best_score、停滞计数、hw_params、问题及策略字段。不存在 `wm_ops init` 命令。schema 是带注释的说明，不能直接作为 JSON 文件拷贝。先 init state 再 session，避免重入时重置历史：

   ```bash
   python3 -B "$WM/state_ops.py" init --evo-dir "$EVO_DIR" --agent "$ROLE" --session-id "$SESSION" --max-rounds "$ROUNDS" --parallel-num "$WIDTH"
   python3 -B "$WM/wm_ops.py" session --wm-path "$EVO_DIR/world_model.json" --session-id "$SESSION" --evo-dir "$EVO_DIR" --op-name "$OP" --requested-rounds "$ROUNDS"
   python3 -B "$WM/wm_ops.py" attach-baseline-evidence --wm-path "$EVO_DIR/world_model.json" --baseline-eval "$EVO_DIR/baseline_evaluation.json"
   python3 -B "$ADAPTER/world_model_adapter.py" --wm-scripts "$WM" --path "$EVO_DIR/world_model.json" --score-base "$SCORE_BASE"
   ```

   `ROLE` 为 `lingxi-evo` 或 `ops-evo`。`session` 会把 completed round 置零，只在新 run 初始化调用。目标可达性检查仅是提示，静态 roofline 或设备地板不是实测上限。

4. 每轮先检查停止条件和 state 中的 drift/must-run 项。完成漂移扩搜索提示后执行 select，并把 JSON 输出写到本轮 `selections.json`：

   ```bash
   python3 -B "$WM/wm_ops.py" select --path "$EVO_DIR/world_model.json" --n "$WIDTH"
   ```

   select 返回 `parallel_index/node_id/parent_solution_ref/...`，**不会替你完成全部节点预约**。由唯一树写入者检查所选 ID 当前均为 open、无重复，然后将它们置 `in_progress`，把完整输出和字符串索引的 `parallel_map.json` 持久化；用本 workflow 的 `scripts/cannbot/reserve_nodes.py --wm-path <world_model.json> --selections <selections.json> --parallel-map <本轮parallel_map.json> --wm-scripts "$WM" --score-base "$SCORE_BASE"` 完成这一有界写操作。预约成功前不派发。整个 round 的映射不因分批运行而改变。每个 lane 完整复制 shared，再以父实现覆盖可优化源码，禁止回写父目录。

   真实 `select_nodes` 在可用模式/候选不足时可能填入未存入树的 `free_N` 项；预约脚本会拒绝它。此时先按 schema 持久化有具体方向的合法候选、验证，再重新 select，不能把虚拟 ID 直接分发。预约中断若已有映射但树尚未提交，应据映射核对并完成同一次预约，不能删除映射重新选择或重复派发。脚本假定编排层是唯一写入者，不提供多进程并发锁。

5. 等所有 lane 结束后，保存编译、精度、全量 case 数、真实时间、源码 diff、`evolved.pipeline`（dict 或 null）。完整 profiling 使用：

   ```bash
   python3 -B "$PROF/msprof_perf_summary.py" --compare --output-dir "$LANE"
   ```

   归置本次 `PROF_GROUP_*/PROF_*/op_summary_*.csv` 到 lane 的 `profiling/`，保留原始文件。该命令不支持源旧文案中的 `--lingxi/--lingxi-output-dir/--diagnose/--task-type`。pipeline 失败按真实缺失反馈，不自动晋级成完整优化结果。

6. 将 `parallel_map.json` 文件内容作为 `MAP` 字符串传给以下 CLI（不是文件路径）；Windows 使用结构化 subprocess 参数，不拼接危险 shell 引号：

   ```bash
   python3 -B "$WM/check_round_artifacts.py" --results-dir "$ROUND_DIR" --shared-dir "$EVO_DIR/shared" --parallel-map "$MAP" --op-name "$OP" --mode "$MODE"
   python3 -B "$WM/wm_ops.py" refine --wm-path "$EVO_DIR/world_model.json" --round "$R" --results-dir "$ROUND_DIR" --parallel-map "$MAP" --task-type "$TASK_TYPE"
   python3 -B "$ADAPTER/world_model_adapter.py" --wm-scripts "$WM" --path "$EVO_DIR/world_model.json" --score-base "$SCORE_BASE"
   ```

   `MODE` 为 `lingxi/ops`；`TASK_TYPE` 为 `vector/cube/cv-mix/unknown`。先解析 artifact checker 的 JSON fail/issues，不能只看退出码；缺 case/结果或伪造通过须纠正为真实失败再 refine，不能跳过门禁。原生 checker 不覆盖 `.asc/native-entry` 时，按[实际产物核查](cannbot-lightweight.md#反馈与收尾)保存等价的真实源码、库身份和正式验证证据；原生适用性与结果单列，不伪造它已通过。refine 会读每个 lane JSON、归一 score、生成子节点与 pending_diagnosis、更新停滞；它不是精度执行器，不验证结果是否来自真实 NPU，证据源还需人工与显式 gate 核对。

7. 对 passed 节点按实际 `facts` 写结构化 diagnosis（区分观察/因果假设/建议），填合法瓶颈词表和 `next_round_hint`；失败项用 `diagnose --failure-type impl_error|strategy_infeasible --failure-reason ...`，而非手工改分数抹去失败。再执行：

   ```bash
   python3 -B "$WM/wm_ops.py" validate-diagnosis --wm-path "$EVO_DIR/world_model.json" --strict
   python3 -B "$WM/wm_ops.py" finalize-ledger --wm-path "$EVO_DIR/world_model.json" --evo-dir "$EVO_DIR"
   python3 -B "$WM/session_anchor.py" update --op-name "$OP" --actual-rounds "$R"
   python3 -B "$WM/state_ops.py" validate --evo-dir "$EVO_DIR" --check-stage-artifacts
   ```

   根据漂移、问题、profiling 证据做下一轮决策。只读报告/人工分析可继续处理缺失指标，但仍须披露对应完整 profiling 门禁未满足，不把缺证据分支称为闭环完成。

8. 完结前 `wm_ops.py session-verify --wm-path ... --evo-dir ...`、state/artifact gate、最佳全量精度与 target/generalization 门禁通过。保存树为 `world_model_final.json`，调用 `evolution-report/scripts/generate_report.py "$EVO_DIR" --pipeline "$ROLE"`，查看输出及 stderr 自检。不得只因为 report HTML 存在就判定任务成功。

## 精度 record / compare 与 ops 分支

精度记录协议和 msprof `--compare` 是两种不同用途：冻结同一输入与可信原始参考输出，再比较候选输出；不能让候选重写 golden 后与自身比较。若上游 generator 已有正式 record 产物，复用其 manifest/输入/参考与容差。当前 `evaluate_ascendc.sh` 和 `verification_ascendc.py` **没有** `--record` 参数，不向它们杜撰该选项；真实 translator verifier 在同一验证流程内加载参考与候选并比较。

lingxi 实际验证脚本位于 `plugins-community/tilelang2ascendc-ops-generator/skills/tilelang2ascend-translator/scripts/evaluate_ascendc.sh`，源角色的 `ops-lab/tilelang-to-ascendc/...` 路径已失效。按准备出的 `.claude/skills` 资源映射执行，并显式设 SOC 与 NPU，避免默认卡 3。Cast/Memcpy 等非计算算子可用原支持的 `--non-compute` 做 bit-exact。

ops 路径先按原 `build_ops.py --repo-root <lane worktree> --op-name ... --soc ... --install-path <绝对路径>` 构建，安装包和 wheel 限于获授权的隔离环境。`build_ops.py` 会清理 build/build_out，不能指向用户共享仓。标准仓及 omni 的 build/namespace/vendor 区别按 ops-evo 角色处理。

原 `evaluate_ops_direct.py` 支持 `--call-spec --baseline-path --evolved-path --device-id --task-type --shapes-mode --target-speedup --eval-lock --eval-lock-timeout --baseline-cache --output`；它在两个独立进程中保存 baseline/evolved 输出再比较，同一设备及 eval lock 保证可比。多 shape 命名全局唯一，修改 default 分支用 `--shapes-mode all`；specialized 分支才可暂用 target，最终仍跑已配置泛化门禁。普通 `evaluate_ops.py` 接口用 `--reference-py/--custom-py`，两者依赖不是相互可替换的“兜底”。

## 依赖与离线验证边界

- 世界模型 CLI、状态、anchor、artifact checker、report 主要为 Python 标准库及同目录 sibling 模块，必须整目录复制。策略 preconditions 的 YAML 路径按运行环境依赖检查。`wm_ops.py` 调用策略/知识库相对路径，须在完整工作副本运行。
- 检查 `evaluate_ops_direct.py` 所需的 `skills/ascendc-evaluation/scripts/AscendPerformanceTest.py:AdvancedPerformanceEngine`，以及 `evaluate_ops.py` 所需的同目录 `evaluate.py:AscendBackend`。若当前 checkout 未提供这些依赖，则该正式评估分支在补齐之前 blocked。不能用 profiler 的时间结果填 precision=true，也不能静默改用未等价的随机/allclose 脚本。
- `wm_ops.py deep-profiling` 依赖所选 checkout 必须另行核实的 `.claude/skills/ascendc-profiling-analysis/scripts/run_deep_profiling.py`。用现有 `ops-profiling --compare` 的 CSV 和已有 `ops-simulator` 分析可提供另一种明确标注的证据；不能伪称旧 deep-profiling 子命令已可运行。
- translator 构建需要 Bash、cmake、make、CANN、torch/torch_npu、编译器及 wheel 构建环境，且会强制安装生成 wheel。ops 构建要对应仓、CANN、真实设备；omni 还要自己的 torch_ops_extension/omni_custom_ops。安装此 skill 不会安装这些组件。
- 可离线运行：合法/非法树验证、真实 select、节点预约重入拒绝、以明确标注为 fixture 的 evaluation_results 测试 refine 的成功/精度失败/缺结果反馈、artifact 检查、state/anchor 和 report fixture。它们仅验证控制逻辑，不能声称 NPU 正确性/性能或完整优化闭环。
