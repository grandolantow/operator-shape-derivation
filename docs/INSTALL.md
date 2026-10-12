# 安装与使用

## 两个独立目录

本仓提供工作流与shape技能；外部CANNBot提供真实生成/进化插件和公共依赖。CANNBot必须是完整checkout，包含plugins-community下的tilelang2ascendc-ops-generator、ops-perf-evolution，以及它们声明的ops/skills、agents、hooks、workflows和模板。只复制SKILL.md不足以运行。

参数`--cannbot-root`显式选择外部checkout，旧`--repo-root`是同义兼容参数；二者都不表示本仓。工作流与shape从安装器所在仓库的skills读取，不从CANNBot/tools取。`--workflow-skill`可覆盖主技能入口，shape仍来自本仓。

## 前置依赖

- 安装器：Python3.10+；Windows PowerShell或Linux Bash。安装不需要PyYAML。
- Codex独立执行：可用Codex和获准Linux工具链，不要求Claude。
- Claude协作：Linux Claude Code及Node、认证/网络配置；API提供商由用户环境决定，不固化。
- 设备执行：配套驱动、CANN Toolkit、编译工具、Python/torch-npu；TileLang路线需TileLang-Ascend及其set_env.sh。核对实际芯片与工具版本，不自动安装/升级。
- benchmark：可读取且可运行的npu-kernelbench或指定框架，依赖、schema与loader按实际版本核验。
- 仅shape静态推导：能读取技能即可，运行检查脚本需要Python3；无需CANNBot、Claude或NPU。

## Windows Codex

```powershell
$workflow = 'C:\work\ascend-op-workflow'
$cannbot = 'C:\work\cannbot-skills'
$task = 'C:\work\tasks\my-op'
New-Item -ItemType Directory -Force -Path $task | Out-Null
python "$workflow\install_codex.py" --cannbot-root $cannbot --task-dir $task
python "$workflow\install_codex.py" --cannbot-root $cannbot --task-dir $task --apply
```

也可运行根目录install-codex.ps1，使用-CannbotRoot（兼容-RepoRoot）。安装器复制任务级.agents/skills、写AGENTS.md路由及manifest，不需要Windows链接权限。打开任务目录新会话，确认ascend-op-workflow可发现。Codex把Claude角色文档作为参考，使用实际可用工具/子agent，不伪造Claude原生hook已运行。

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

```bash
bash "$workflow/launch-claude.sh" --task-dir "$task" --task-file TASK.md
```

启动器使用IS_SANDBOX=1和--dangerously-skip-permissions，代理/认证沿用进程环境，不读取其他进程凭据或写全局配置。--resume使用最近会话，必须先核实任务cwd与最近会话确为目标；不要在多会话情况下盲用。启动后实际验证技能/agent加载和工具执行，不把配置存在当运行成功。

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
范围：full；合格G冻结后继续真实进化，不在交接处停止。
默认R/G≥1.2，固定G/O≥1.5，最多5轮×5候选；资源与看护遵循已有授权。
```

仅做shape或仅生成时写明范围。阶段、目标及证据完整规则见主skill，不用重复手填已经确定的条件。
