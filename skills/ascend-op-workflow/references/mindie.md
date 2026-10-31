# MindIE 入口与默认 Codex 执行

用户从 `/mindie-agent`（Codex 也可用 `$mindie-agent`）描述算子任务，当前 Agent 发现并读取 `ascend-op-workflow/SKILL.md` 后按其阶段执行。这里是调用协议，不是后台调度服务；`prepare/link/show` 不启动生成、模型或 NPU。

## 入口与依赖

将独立 workflow 仓的技能安装到任务工作区，并在该工作区打开新会话。默认安装只需 Python：

```bash
python /path/to/workflow/install_codex.py --task-dir /path/to/task --apply
```

任务目录须已存在；未知 AGENTS.md/已有托管内容冲突沿用安装器的报错，不覆盖个人配置。已有工作区可保留其配置并将 workflow 技能路径作为明确引用。不要修改全局 MCP 或将 workflow 复制回 CANNBot。

生成/优化需要 CANNBot 时，先查本任务合同、安装 manifest 或已指定路径。已有可用 checkout 就复用；缺少时询问“是否安装 CANNBot，或指定已有仓库？”用户选择安装后，读取该版本安装说明并复用原入口，限定安装位置；拒绝则继续 shape/workload，不尝试启动依赖缺失的阶段。与原环境匹配的编译/benchmark 依赖按需检查，不重装整套环境。

若本地和远端分别持有 checkout，分别记录实际根与版本；默认 Codex 只读其资源，不要求 Claude/Node。`install_codex.py --cannbot-root PATH` 可在新任务安装时额外复制该版本声明的技能作为快照；不是运行时必需操作，也不修改 CANNBot。完整源码仍须在实际执行环境可读。

启动时提示：生成与多轮优化的 token 消耗较大，默认 Codex，建议常规代码模型和中等 effort；Claude 可选。已有执行授权直接推进，不为每个候选重复询问。

## 从准备到真实执行

1. **输入与 workload**：按主 Skill 推导 shape，准备 definition/reference/inputs/workload，使用实际 benchmark schema/loader 检查。冻结完整 case、oracle、R、计时协议、写范围和预算。通过原 `workflow.py init/prepare generation` 记录父任务与 preparation。
2. **Codex 生成**：读取 CANNBot 的 `plugins-official/ops-direct-invoke/AGENTS.md`、四个 `agents/ascendc-kernel-*.md` 及 `workflows/task-prompts.md`。按原始模板实施环境、设计、设计审核、开发、代码审核、修复、全量验证和报告步骤；使用原生子 agent 承接角色，记录角色复用和审核独立性。所有新实现直接生成 AscendC，不进入 TileLang 设计/转译。Claude 专属语法由实际 Codex 工具承接；模板和 SDK 来源保持只读，不能以读取入口替代实际分阶段执行。
3. **冻结 G**：真实生成和完整验证完成后，用 `freeze/result generation` 归档 G 与原始证据。G 全量正确且正式性能有效即可交接；生成目标未达记录 TARGET_UNMET，不伪造通过，也不阻止已授权优化。已有匹配 AscendC 时按原复用合同跳过生成。
4. **Codex 优化**：用固定 G 创建 `prepare optimization`；先读本 workflow 的[CANNBot 执行适配](cannbot-execution.md)，默认走轻量入口，显式 native 或已有原生 state/anchor 才沿用完整模式。读取外部 CANNBot 的 `agents/lingxi-evo.md` 或 `agents/ops-evo.md` 及相应 partial 作为角色参考；使用该 checkout 的真实世界模型/评测脚本，以及随本 workflow 安装的评分兼容、预约和适用的全量守卫。策略选择、候选执行、评测回树均须真实发生。Claude 专属语法由当前宿主真实工具承接，不启动 Claude 以满足角色名，也不另写搜索状态机。
5. **回收**：按合同完整复测最终 O，使用原评测器生成同条件 G/O 证据，`freeze/result optimization/verify` 收尾。原内部 score 的分母若是 PyTorch，保留其含义；正式优化目标仍是固定 G/O。精度、有效性能、目标达成分别报告，预算结束可交付 TARGET_UNMET。

必要适配由本 workflow 的 `scripts/cannbot/` 和执行参考统一维护并随技能安装；不依赖原开发机的 `tools/cannbot-codex`、vendor 或私有 source manifest。执行环境须能读取已安装 workflow 和指定 CANNBot checkout，本地/远端各自解析路径并记录版本。不得修改 CANNBot 的脚本、模板、Skill/Agent/Hook、已有脏文件或其中的 workflow 副本。若现有接口不能支撑步骤，报告具体限制。例如需要保留 profile 时，已知 quick shell 包装未透传 `--keep-prof`，可直接调用原 `msprof_perf_summary.py` 的对应 Python 入口，不修共享包装器、不复制评测器。

## 远端作业与关联

启动远端生成/优化前，确认 MindIE 原生远端工具可用；失败时报告具体错误，先排查环境配置。

使用已指定环境，先按环境池完成预检，再用 MindIE 原生 remote-dev 提交命令到准确 alias/容器/cwd。原生工具管理真实进程和取消，workflow 只记录回执。查询状态使用原工具，不从关联文件推断任务仍在运行。

```bash
python "$WORKFLOW_CLI" link --run "$RUN" --preparation "$PREPARATION_ID" \
  --job-id "$JOB_ID" --endpoint "$ENDPOINT" --container "$CONTAINER" \
  --executor codex --model "$ACTUAL_MODEL" --effort "$ACTUAL_EFFORT"
python "$WORKFLOW_CLI" show --run "$RUN"
```

`WORKFLOW_CLI` 是独立 workflow 的 `skills/ascend-op-workflow/scripts/workflow.py`；其他变量取自当前任务与真实回执。模型/effort 无法观测时省略参数并在任务说明中标明，不猜。原生 exec 的 session_id 可作为工具作业标识，不能填成 Claude session；一个阶段可关联多个实际作业。只有实际建立进化目录后补 `--evo-dir`，产出后补 `--artifact`，正式归档后补 `--result`。持续日志仅保存路径，完整性由正式归档负责。

`execution-links.json` 连接 preparation → job → evo_dir → result，由一个父任务协调者写入；不存作业生命周期、另一棵世界树或预算。轻量 `show/link` 不哈希完整归档，不能替代最终 `verify`。

重连先 `show` 定位原 job，查询真实执行层和原 `state.json`/checkpoint；运行中的继续观察，已退出的从未完成阶段续接。沿用原父任务、preparation、世界树、固定 G 和已用预算，不因断线重提任务。取消只针对本任务真实回执对应的作业，使用执行层原接口并核实子进程退出。

## Claude 选配与已有验收

明确选择 Claude 后才使用 `init_claude_workflow.py` / `install-claude.sh` 注册其任务级资源。`launch-claude.sh` 显式接收 `--model`、`--effort`、可选 `--agent`，恢复用 `--resume SESSION_ID` 指定精确原会话。代理/认证继承进程环境，不读取 root 配置或跨机传凭据。关联填写 `--executor claude --claude-session ACTUAL_SESSION`。

阶段 4 在 Claude Code 2.1.261 print 模式实跑时发现 600 秒后台等待上限，任务级设置 `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0`，并用原 Hook 支持的 `LINGXI_EVO_DIR` 恢复精确进化目录；它们只在适用 Claude 版本/模式下使用，不配置到默认 Codex 路径。任务预算和执行层取消继续生效。

历史 Claude SDPA 案例使用 50 个 case、三轮进化，固定 G/O=1.1044×，目标 1.5× 未达。2026-10-28 默认 Codex 案例已完成新 workload、新生成 G、一轮一个候选 O、完整复测和父任务归档；G/O 均通过原始 50 例精度及 24 项双流检查，父归档 `verified=true`。同窗口固定 G/O=1.017841574×，目标 1.5× 未达；没有独占租约，性能为临时测量，不能声称稳定收益。原内部 R/O=0.5133 的分母是 PyTorch，不能替代固定 G/O。

随后在独立原生 Codex 新会话验证了 `$mindie-agent` 发现并读取入口、任务级 workflow 和安装 manifest，以及缺少 CANNBot 时的询问、拒绝安装后继续准备 workload、指定已有 checkout 后只读确认入口。拒绝分支的 workload 只做标准库 JSON/shape 检查，没有冒充 benchmark loader 验证。Linux 根测试 28 项、workflow 13 项、两个技能结构校验均通过。短 CPU 作业验证了独立客户端重新连接原 job、取消后的父子进程清理及不影响另一作业；原生成/优化归档重新查询、验证后保持不变。这些检查不等同于强制网络中断下的在途优化恢复、coordinator 租约或多宿主验收。

## 已知限制与交付状态

历史所测 CANNBot 版本的原世界树校验拒绝 `best_score<1`，即使候选全量正确、搜索状态已完成；原 HTML 报告在 `hw_params=null` 时抛出异常。这两项在上述案例中均失败。当前 workflow 已内置窄兼容：对明确 PyTorch 分母的有限正分数，调用原生 validator 并仅过滤已知分数下限错误，原生结果单列；未知结构错误仍拒绝。不改 CANNBot、不钳制分数、不重写其 schema/validator。历史失败记录保留，离线兼容回归不等于原任务已完成。只有归档通过时，不得汇报“全部门禁通过”。

HTML 是可选展示产物；失败时继续交付 Markdown 结论、源码、case、JSON 结果和原始日志，并明确报告未生成 HTML。归档完整性、全量正确性、性能测量有效性、目标达成、原工具校验/报告状态分别说明。缺失或失败的必要精度/评测步骤仍阻止相应阶段通过；可选报告失败不能覆盖已完成的真实执行结果。

本机验收遇到 Windows shell `CreateProcessWithLogonW 1385`，通过对必要命令使用宿主自动审批完成入口读取；当前桌面 MindIE remote-dev 工具另报 `release.update/harness_readback` 路径检查错误，103 的短作业检查使用已配置的环境池 remote-dev。它证明执行组件可用，不证明有故障的插件工具已修复。安装/宿主环境问题须按实际环境解决，不通过修改 CANNBot 或全局配置的隐式回退掩盖。
