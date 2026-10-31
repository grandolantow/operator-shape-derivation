# 安装与使用

## 两个独立目录

本仓可独立安装工作流与shape技能；外部CANNBot在生成/优化阶段提供执行参考、工具和公共依赖。需要时复用完整checkout，包含plugins-official/ops-direct-invoke、plugins-community/ops-perf-evolution及其依赖。只复制SKILL.md不足以运行生成/优化。CANNBot源码与已有配置保持不动。

参数`--cannbot-root`可选：提供时将外部checkout声明的技能一并安装为任务快照；省略时只安装本仓workflow/shape，生成或优化需要时再由Skill询问安装或指定已有位置。旧`--repo-root`是同义兼容参数；二者都不表示本仓。工作流与shape从安装器所在仓库的skills读取，不从CANNBot/tools取。`--workflow-skill`可覆盖主技能入口，shape仍来自本仓。

## 前置依赖

- 安装器：Python3.10+；Windows PowerShell或Linux Bash。安装不需要PyYAML。
- Codex独立执行：可用Codex和获准Linux工具链，不要求Claude。
- Claude协作：Linux Claude Code及Node、认证/网络配置；API提供商由用户环境决定，不固化。
- 设备执行：配套驱动、CANN Toolkit、编译工具、Python/torch-npu；生成直接使用 AscendC。核对实际芯片与工具版本，不自动安装/升级。
- benchmark：可读取且可运行的npu-kernelbench或指定框架，依赖、schema与loader按实际版本核验。
- 仅shape静态推导：能读取技能即可，运行检查脚本需要Python3；无需CANNBot、Claude或NPU。

## Windows Codex

```powershell
$workflow = 'C:\work\ascend-op-workflow'
$task = 'C:\work\tasks\my-op'
New-Item -ItemType Directory -Force -Path $task | Out-Null
python "$workflow\install_codex.py" --task-dir $task
python "$workflow\install_codex.py" --task-dir $task --apply
```

也可运行根目录install-codex.ps1，使用-CannbotRoot（兼容-RepoRoot）。安装器复制任务级.agents/skills、写AGENTS.md路由及manifest，不需要Windows链接权限。打开任务目录新会话，确认ascend-op-workflow可发现。Codex把Claude角色文档作为参考，使用实际可用工具/子agent，不伪造Claude原生hook已运行。

Linux Codex 同样运行 `python3 "$workflow/install_codex.py" --task-dir "$task" --apply`，不需要 Claude 或 Node。已有任务配置不覆盖；如有 AGENTS.md 冲突，可保留原文件，在其中引用本仓技能入口。运行时缺少 CANNBot 则先询问；选择安装后复用该版本原安装入口，拒绝时继续 shape/workload，明确生成/优化尚不可执行。无需为运行时指定 CANNBot 重新覆盖安装 manifest。

MindIE 入口、默认 Codex 的真实生成/进化和作业关联见 [MindIE 接入参考](../skills/ascend-op-workflow/references/mindie.md)。执行前提示 token 成本较大，建议常规代码模型和中等 effort；Claude 仅在明确选择后配置。

## 内置 CANNBot 适配

四个适配脚本和轻量/原生执行说明随 `.agents/skills/ascend-op-workflow` 整体安装，内容哈希包含在原 manifest 中；不需要独立的 `cannbot-codex` 包，也不携带 vendor。生成/优化时指定当前执行环境中的完整 CANNBot checkout；远端同时部署 workflow 技能和 CANNBot，不复制本机绝对路径。

`--cannbot-root` 指定的是原始 CANNBot checkout，不是适配包。其原始技能快照作为参考，Codex 优化优先按 workflow 的[执行适配入口](../skills/ascend-op-workflow/references/cannbot-execution.md)选择轻量/native，调用本技能的脚本；无需另注册同名 `ops-perf-evolution` 适配 skill。首次在新环境可运行 `python <已安装技能>/scripts/cannbot/prepare_workspace.py --help` 检查入口，再按实际需要准备任务资源。安装不启动作业、不安装 CANN/torch-npu，也不保证外部 evaluator 缺失依赖已补齐。

## Linux Claude

```bash
workflow=/workspace/ascend-op-workflow
cannbot=/workspace/cannbot-skills
task=/workspace/tasks/my-op
mkdir -p "$task"
bash "$workflow/install-claude.sh" --cannbot-root "$cannbot" --task-dir "$task"
bash "$workflow/install-claude.sh" --cannbot-root "$cannbot" --task-dir "$task" --apply
```

初始化合并任务级skills、agents和hooks，注册CLAUDE.md路由及manifest；不会执行两个插件的init.sh。源技能使用链接，两个源码目录要保留在安装时位置。准备TASK.md并确认授权后才运行：

生成侧 SessionStart 使用任务级只读上下文脚本加载原生 AscendC 入口和资源路径；不执行原 Hook 的 devkit 克隆逻辑。SDK须按当前环境发现并记录，源码 Hook 仅保留供查阅。

```bash
bash "$workflow/launch-claude.sh" --task-dir "$task" --task-file TASK.md --model "$model" --effort "$effort"
```

启动器使用IS_SANDBOX=1和--dangerously-skip-permissions，代理/认证沿用进程环境，不读取其他进程凭据或写全局配置。`model`/`effort` 取当前任务选择；可用 `--agent NAME` 指定已初始化的原Agent，`--resume SESSION_ID` 精确恢复原会话，不使用最近会话。启动后记录并核验实际模型与effort、技能/agent加载和工具执行，提供商拒绝时不静默替换，不把配置存在当运行成功。

## 环境安装脚本

保留根目录agent_ops_init.sh供显式环境准备。它可能安装系统/Python包、克隆或更新TileLang并写入~/.bashrc；集中init不调用它。先阅读脚本及--help，再按环境授权决定是否执行。

CANN只检查不安装；脚本注释中的torch_npu、Node和Claude安装并未完整实现，不能把它当完整依赖保障。PyTorch安装分支的规格引用存在历史问题，已有配套环境直接复用。工作流本身不修改该历史安装逻辑。

## 版本更新与冲突

同一任务再次apply必须内容与manifest一致。源码版本变化、原托管文件修改或未知文件占位会报冲突，不覆盖。要使用新版本，建立新安装目录并迁入任务的合同/检查点与剩余预算，或人工审查后处理冲突；不能把安装新目录当重置搜索预算。旧运行任务继续绑定其原源码身份，不在运行中替换链接源。

## 发起任务

```text
使用ascend-op-workflow完成<算子路径/入口>。
Codex负责第0～4阶段；第5～7阶段选择<Codex独立 / Codex＋Claude协作>。
输入材料：<源码、配置、profiling>；环境：<已核实的环境/容器/cwd>。
路线：<整算子 / C→V串行>，优先复用成熟实现。
范围：auto；首次全量正确立即冻结G，实测达标交付，未达标进入已授权进化；明确要求持续优化时指定full。
默认R/G≥1.2，固定G/O≥1.5，优化最多5小时有效执行、5轮×5候选；资源与看护遵循已有授权。
```

仅做shape或仅生成时写明范围。阶段、目标及证据完整规则见主skill，不用重复手填已经确定的条件。
