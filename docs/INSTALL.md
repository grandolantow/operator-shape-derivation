# 安装与使用

默认使用 **MindIE Agent / Codex + 直接 AscendC + 轻量优化**。已有配套 Ascend 环境时，只需安装本仓技能并指定完整 CANNBot 路径；不需要再安装独立 adapter。可直接使用下方的[一键安装提示词](#让-mindie-agent-完成安装)。

## 两个独立目录

本仓可独立安装工作流与shape技能；外部CANNBot在生成/优化阶段提供执行参考、工具和公共依赖。需要时复用完整checkout，包含plugins-official/ops-direct-invoke、plugins-community/ops-perf-evolution及其依赖。只复制SKILL.md不足以运行生成/优化。CANNBot源码与已有配置保持不动。

参数`--cannbot-root`可选：提供时安装外部checkout中生成/优化入口及角色声明的技能，排除 GitCode 仓库协作技能；省略时只安装本仓workflow/shape，生成或优化需要时再由Skill询问安装或指定已有位置。旧`--repo-root`是同义兼容参数；二者都不表示本仓。工作流与shape从安装器所在仓库的skills读取，不从CANNBot/tools取。`--workflow-skill`可覆盖主技能入口，shape仍来自本仓。

## 按阶段准备依赖

本地宿主负责读取技能和调度；Linux 执行环境负责构建、验证和测量。两者可以是同一台机器，也可以通过 MindIE 原生远端工具连接；Windows 本地安装成功不代表远端已经就绪。

| 使用范围 | 必要依赖 | 安装或检查方式 |
| --- | --- | --- |
| 安装 workflow | Python 3.10+、本仓完整源码；克隆时需要 Git 和仓库访问权限 | `install_codex.py` 仅用标准库；已有源码不要求联网 |
| 读取技能、shape 静态推导 | 能发现任务级技能的 MindIE Agent / Codex；输入源码、配置 | 在任务目录打开新会话，确认读取 `ascend-op-workflow/SKILL.md` |
| 生成与优化参考 | 完整、可读的 CANNBot checkout | 核对 `plugins-official/ops-direct-invoke/`、`plugins-community/ops-perf-evolution/` 及其引用的 `ops/`、`infra/`；只复制 SKILL.md 不够 |
| 直接 AscendC 工程 | Linux、Bash、所选模板要求的 CMake/构建工具与 C++ 工具链；配套 CANN Toolkit 的 AscendC 编译器、头文件和库 | 读取该版本生成入口、模板与环境检查；核对实际芯片、SoC 和编译目标 |
| API 文档与开发模板 | 生成流程所用 asc-devkit 文档、示例及 CMake 资源 | 优先复用已有 SDK，按所选版本说明设置 `ASC_DEVKIT_DIR`；它不是 workflow 安装器自动下载的内容 |
| 上板运行 | 可用 Ascend NPU、配套驱动/运行时、设备访问权限 | 在实际执行容器核对 `npu-smi info`、CANN 环境及获准设备；不在 Windows 宿主安装 NPU 软件 |
| PyTorch reference / Torch 接入与正式评测 | 与芯片、CANN、Python 匹配的 torch / torch-npu；所选 benchmark / verifier 的依赖 | 使用已有配套环境；在同一解释器检查 import、真实 loader 和评测入口。纯 C++ 直调阶段不单独要求 Torch |
| 轻量优化 | 上述生成与评测环境、CANNBot 原生 world-model / 策略资源、本仓内置适配脚本 | 按需准备任务副本；默认不要求另一套进化服务、HTML 或全量 PMU |
| MindIE 远端执行 | 已安装可用的 MindIE 原生远端工具及目标连接配置 | 按环境池核对 alias / endpoint / 容器 / cwd，完成只读预检；配置文件存在不等于连接成功 |
| 设备租约（执行路径需要时） | MindIE 官方 coordinator 组件及可用入口 | 已有组件直接复用，检查 `mindie-coordinator --help` 或该版本配置的组件入口；组件的 Python 要求以自身元数据为准。正式占卡前验证租约，不为安装技能申请设备 |

版本随实际芯片、CANNBot 和 benchmark 选择，不能无条件安装最新 torch/torch-npu 或从其他环境复制版本组合。原生 evaluator 的附加 Python 依赖以其 `requirements` 和实际 import 为准；缺少包时在任务虚拟环境按对应版本说明补齐，复用现有配套 Torch 环境时不要让安装过程替换其 Torch/CANN 组合。记录所用版本与可访问的包源，不把其他插件的 requirements 当本流程依赖。

例如，所选 CANNBot evaluator 若引用 `AscendPerformanceTest.py` 或 `ascendc-evaluation/scripts/evaluate.py`，须核对这些资源真实可读且可导入；缺失时按该版本说明补齐，不推测它们对应同名 PyPI 包。直接 AscendC 工程可以使用合同指定的正式 verifier，不为安装 workflow 补齐所有评测分支。具体入口见[执行适配的依赖边界](../skills/ascend-op-workflow/references/cannbot-execution.md#依赖边界)。

以下内容**不是默认依赖**：Claude / Node / Claude Hook、TileLang 设计转译工具链、独立 `cannbot-codex` 包、HTML 报告依赖。Claude 协作、PMU、仿真或 HTML 仅在实际选择时准备。安装器和本仓适配脚本不依赖 PyYAML；外部脚本是否需要它按所选入口检查。

## 让 MindIE Agent 完成安装

在准备使用 workflow 的任务工作区打开 MindIE Agent，复制以下提示词即可。默认安装本仓技能，并检查生成/优化依赖；有已知 CANNBot、benchmark、SDK 和远端位置时附在末尾。无需先手工安装所有可选插件。

```text
请为当前任务工作区安装并检查 ascend-op-workflow。
仓库：https://github.com/grandolantow/operator-shape-derivation.git
版本：优先使用当前对话提供的源码 checkout（含未提交改动），记录 HEAD 和工作区状态；没有可用 checkout 时再克隆 main，若我另有指定则使用指定分支或提交。
执行方式：MindIE Agent / Codex，直接 AscendC，默认轻量优化。

1. 读取该仓 README.md 和 docs/INSTALL.md。复用可用且无冲突的 checkout，
   否则克隆到当前工作区的 .tools/operator-shape-derivation；记录实际提交 SHA。
   已有运行任务继续绑定原技能版本，不在运行中替换源码或安装副本。
2. 确认任务目录已存在（新建任务先创建目录）。用 Python 3.10+ 执行
   install_codex.py，以当前任务目录为 --task-dir，
   先预览，正常则直接加 --apply 完成任务级安装，无需再次确认常规安装。
   安装完整技能和内置适配脚本，不只复制 SKILL.md。若已有 AGENTS.md 或
   托管文件冲突，保留原内容并报告具体冲突；可保留原配置，明确引用
   源码中的 skills/ascend-op-workflow/SKILL.md，但不能把它报成复制安装成功。
3. 从任务合同、安装清单或我提供的位置复用完整 CANNBot、benchmark、SDK。
   用于生成/优化且已知 CANNBot 路径时，第 2 步优先带 --cannbot-root 一起
   安装生成/优化依赖（不安装 GitCode 仓库协作技能）；仅做 shape 或尚无
   路径时先完成本仓安装。
   缺少 CANNBot 时一次性询问已有路径，或其源码地址与获准安装位置；
   未提供则先完成 workflow 安装，列出生成/优化缺项，不猜测私有仓库地址。
   CANNBot 源码保持只读，必需的可写资源放到任务工作目录。
4. 复制安装时检查 manifest、技能及 scripts/cannbot 的文件哈希，运行已安装
   workflow.py --help 和 prepare_workspace.py --help，验证入口可用；采用明确
   引用方式时核对源码中的完整技能，并从该源码目录运行相同入口检查。
   若存在指定的 Linux 执行环境，先遵循环境池与只读预检，再检查原生
   远端工具、CANN/编译器、SDK、Torch 及真实 benchmark/verifier 依赖；
   本地/远端分别记录路径和版本。设备租约路径需要 coordinator 时，
   检查现有官方组件入口，缺失按该 MindIE 版本原说明准备任务级安装。
   普通缺失 Python 包可在任务虚拟环境按实际 requirements 安装并记录版本；
   系统驱动/CANN、现有 Torch 组合及共享宿主配置的变更先列出方案。
   没有指定执行环境时，只安装本地技能并列出尚未检查的运行依赖。
5. 安装不启动生成、优化、编译或 NPU 测试；不修改 MindIE Agent / CANNBot
   源码，不安装默认路径不需要的 Claude、Node 或 TileLang。
   最后报告：源码提交、实际技能路径、安装/明确引用方式、入口检查结果、
   运行依赖的已确认项/缺项/未检查项，以及新会话的触发示例。
```

这段提示词负责调度现有安装器及对应版本的依赖准备，不是跨所有芯片/系统自动安装 CANN 的脚本。缺少网络、源码权限或目标环境信息时，报告具体缺项并完成独立的本地安装，不宣称整套环境已可运行。

## 一条命令安装技能

已有完整 workflow 源码和空任务目录时，一条命令即可安装：

```bash
python3 /path/to/workflow/install_codex.py --task-dir /path/to/task --apply
```

去掉 `--apply` 为只读预览。安装器不创建任务根目录，不下载依赖、不执行插件 init、不启动 Agent 或设备作业；它复制完整任务级 `.agents/skills/`，写入 `AGENTS.md` 路由及 `.agents/ascend-op-workflow-install.json`。再次以同参数运行会检查已安装内容与清单一致；**没有 `--update` 或强制覆盖选项**。

生成/优化且已有完整 CANNBot checkout 时，优先一起安装对应依赖技能：

```bash
python3 /path/to/workflow/install_codex.py --task-dir /path/to/task --cannbot-root /path/to/cannbot --apply
```

`--cannbot-root` 安装该版本生成/优化入口及角色声明的技能快照，Codex 和 Claude 安装器均排除 `gitcode-*`（PR、Issue、仓库工具），并记录实际安装来源与哈希。其余生成、精度、调试、评测、profiling 和进化依赖保留；报告等技能资源仍可供对应阶段使用，复制技能不会自动安装 HTML/PMU 等可选运行依赖。它不下载 CANNBot，也不把完整编译环境装进任务目录。没有 checkout 时先提供源码地址和获准安装位置；已有完整源码可以直接复用，不必重复克隆。只装本仓技能适合 shape 或暂缺依赖的阶段，不能把它报成生成/优化依赖安装齐全。已安装旧版本的任务不能直接覆盖 manifest；使用新任务安装目录，保留原任务内容。

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

## 安装后检查与首次使用

在任务目录运行本地 CPU 入口检查（Windows 将 `python3` 换成 `python`）：

```bash
python3 -B .agents/skills/ascend-op-workflow/scripts/workflow.py --help
python3 -B .agents/skills/ascend-op-workflow/scripts/cannbot/prepare_workspace.py --help
```

核对 `.agents/ascend-op-workflow-install.json` 的 `workflow_repo_root`、可选 `cannbot_root` 和 `entries` 来源/哈希；以同一源码和参数重跑安装器可以校验托管内容。`--help` 不会准备资源、分配设备或验证 CANN；主机上的 Python import 成功也不代表容器中的解释器可用。

在任务目录打开新会话，确认能发现 `ascend-op-workflow`。然后发起：

```text
/mindie-agent 使用 ascend-op-workflow 开发 <源码路径、算子入口>。
目标环境：<环境、容器、工作目录>；CANNBot：<该执行环境中的路径>。
准备 workload，直接生成 AscendC，按 auto 验收；需要优化时最多一轮。
```

若因已有配置冲突选择了明确引用源码，在请求中附上该 checkout 中 `skills/ascend-op-workflow/SKILL.md` 的实际绝对路径，要求 Agent 读取后执行；这不依赖自动发现，也不会生成安装 manifest。

已安装内容能读取、入口检查通过，可报告“workflow 安装完成”。构建/设备/评测依赖必须在实际执行环境分别确认；未做真实构建和全量验收时，报告“未实跑”，不能以安装成功推断生成/优化已跑通。首个全量正确 G 冻结和后续实测验收规则不变。

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
