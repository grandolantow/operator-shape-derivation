# Ascend 算子工作流使用说明

在任务目录打开 Codex 或 MindIE Agent。先选本次做到哪一步，再安装技能并发起任务。**任务目录**保存技能、输入、设计和运行记录。**执行目录**负责构建、测试和 NPU 测量，可以在另一台机器的容器里。

## 1. 选择任务范围

| 你想拿到什么 | 怎么发起 | 交付物 |
| --- | --- | --- |
| shape 和测试用例 | 使用 `operator-shape-derivation` | 推导说明、可重跑脚本和 workload |
| 实现方案，先给人评审 | 要求提交 `DESIGN.md` 后暂停 | 成熟实现调研、复用判断、tiling 和同步方案 |
| 可验收的首版 AscendC | `generation_only` | 实现、全量精度、正式性能和冻结版本 `G` |
| 首版达标即交付，未达标再优化 | 默认 `auto` | 达标交付 `G`，具备条件且获准时继续优化 |
| 明确要做性能优化 | `full` | 冻结的 `G`、优化候选和可复现的对比结果 |
| 演练任务交接 | `rehearsal` | 独立的演练记录和模拟交接产物，停在优化准备阶段 |

## 2. 安装和换版本

### 一句话交给 agent 安装

```text
请从 https://github.com/grandolantow/operator-shape-derivation 的 main 为当前任务目录安装 ascend-op-workflow，用官方 install_codex.py 先预览再应用，检查安装清单和两个 CLI 入口，最后告诉我实际提交、安装路径和缺少的运行依赖，本次只做安装检查。
```

可把“当前任务目录”换成绝对路径。默认安装 CANNBot `master` 配套技能。要复用指定版本，在末尾加“用 `--cannbot-root` 指定 CANNBot <绝对路径>”。只做 shape 或需要离线安装时，加 `--workflow-only`。

### 自己运行安装脚本

准备 Git 和 Python 3.10 或更新版本。把示例路径换成自己的目录。如果已有源码 checkout，命令使用其当前检出的版本。看清分支、提交和预览的目标目录，再执行带 `--apply` 的命令。[依赖和安装细节](INSTALL.md)

**Windows PowerShell**

```powershell
$workflow = 'C:\work\operator-shape-derivation'
$task = 'C:\work\tasks\my-op'
if (-not (Test-Path -LiteralPath $workflow)) {
    git clone --branch main https://github.com/grandolantow/operator-shape-derivation.git $workflow
}
git -C $workflow status --short --branch
git -C $workflow rev-parse HEAD
New-Item -ItemType Directory -Force -Path $task | Out-Null
python "$workflow\install_codex.py" --task-dir $task
```

```powershell
python "$workflow\install_codex.py" --task-dir $task --apply
Set-Location -LiteralPath $task
Get-Content -LiteralPath .agents/ascend-op-workflow-install.json
python -B .agents/skills/ascend-op-workflow/scripts/workflow.py --help
python -B .agents/skills/ascend-op-workflow/scripts/cannbot/prepare_workspace.py --help
```

**Linux Bash**

```bash
workflow="$HOME/work/operator-shape-derivation"
task="$HOME/work/tasks/my-op"
if [ ! -e "$workflow" ]; then
    git clone --branch main https://github.com/grandolantow/operator-shape-derivation.git "$workflow"
fi
git -C "$workflow" status --short --branch
git -C "$workflow" rev-parse HEAD
mkdir -p "$task"
python3 "$workflow/install_codex.py" --task-dir "$task"
```

```bash
python3 "$workflow/install_codex.py" --task-dir "$task" --apply
cd "$task"
cat .agents/ascend-op-workflow-install.json
python3 -B .agents/skills/ascend-op-workflow/scripts/workflow.py --help
python3 -B .agents/skills/ascend-op-workflow/scripts/cannbot/prepare_workspace.py --help
```

安装后从任务目录开新会话，请 agent 回报实际读取的 `ascend-op-workflow/SKILL.md` 路径。两个 `--help` 检查的是本地命令入口。生成和上板前，还要在实际执行环境核对 CANNBot、CANN、编译器、设备和 benchmark。已有 CANNBot 在目标容器内时，开工前提供容器里的实际路径。

**换分支或提交。** 安装脚本把技能复制到任务目录，源码 checkout 切分支后需要重新检查任务使用的版本。先用目标版本的安装器预览。若旧副本与新版本冲突，保留旧任务，在新任务目录安装。直接从源码读取技能的任务，按实际读取的 checkout 核对提交。

## 3. 发起和推进任务

准备好源码入口与提交、算子语义与边界、代表性 shape 和 dtype、执行环境、性能参考与计时边界。把下列提示词里的占位内容替换成实际信息，每次复制当前需要的一段。

### 共享环境只读预检

```text
请先对 <环境别名> 的 <容器和工作目录> 做只读预检，核对 SoC、获准设备、CANN、CANNBot 和 benchmark 的版本及路径，列出能运行的阶段和缺少的依赖，本次停在环境检查。
```

### 发起单算子任务，先审设计

```text
用 ascend-op-workflow 做 <算子名>，模式为 <generation_only / auto / full>。
原实现是 <仓库、提交、文件和函数>，算子边界是 <输入、输出及需保持的状态>。
用例来自 <模型配置、workload 或 profiling 路径>，重点覆盖 <shape、dtype、layout 和边界>。
执行环境为 <别名、容器、工作目录和获准设备>，依赖路径是 <CANNBot、CANN 源码和 benchmark>。
性能参考为 <实现或调用链>，计时边界为 <kernel / 完整算子调用 / graph replay>，目标及预算为 <填写或沿用默认>。
请先确认 shape 和算子契约，调研已有实现并提交 DESIGN.md，等我审查后再写实现。
```

评审时先看 `OPERATOR_CONTRACT.md` 中的接口、精度、状态、用例和计时边界，再看 `DESIGN.md` 里的源码来源、复用范围和同步设计。设计走读和 `design_check.py` 的结果用于确认能否交给开发。复用和双缓冲的具体检查项见下方附录。

### 设计通过后继续

```text
设计已通过，请按 DESIGN.md 和 OPERATOR_CONTRACT.md 继续生成并验收，先交付全量精度和正式性能，按当前模式与预算决定是否继续优化。
```

## 4. 验收和续跑

- **精度**按冻结契约跑全量用例。看通过数、总数和失败项。有状态或原地写回时，检查测试用的初始状态和写回结果。
- **性能**对新建正式任务预先冻结 10 个性能 case，超大 case 最多 3 个。比较同设备、同用例、同运行模式和同计时边界下的逐 case 耗时，核对实际加载的代码或库、原始日志和复现命令。
- **目标**用原实现或调用链 `R`、首次全量精度通过并冻结的 AscendC 实现 `G`、优化候选 `O` 来计算。默认生成目标为 `R/G` 几何平均加速比 ≥1.2，默认优化目标为 `G/O` ≥1.5。
- **预算**默认累计活跃时间最多 5 小时、最多 5 轮、每轮最多 5 个候选。到预算仍未达目标时，交付最优合格版本、测量结果和 `TARGET_UNMET` 状态。[标准工作流](WORKFLOW.md)

### 验收提示词

```text
请验收 <任务目录> 的 <算子>。按冻结契约报告编译状态、精度通过数和失败 case；按冻结性能集报告逐 case 耗时、几何平均加速比和目标达成状态。附实际加载的代码或库版本、计时边界和原始日志。优化任务补充相对冻结 G 的表现及已用预算。
```

### 从已有任务续跑

```text
请恢复 <原任务目录> 中的 ascend-op-workflow。先看合同、交接、日志和活动作业，找到第一个未完成检查。沿用原契约、冻结基线和剩余预算继续，已有作业在跑就先跟踪它，结束后更新交接和证据路径。
```

在任务目录可查看和核对工作流归档。替换 `<运行记录路径>` 为交接给出的实际路径。Linux 上如果解释器命令为 `python3`，将下列 `python` 替换为 `python3`。[归档 CLI](../skills/ascend-op-workflow/scripts/CLI.md)

```text
python -B .agents/skills/ascend-op-workflow/scripts/workflow.py inspect --run "<运行记录路径>"
python -B .agents/skills/ascend-op-workflow/scripts/workflow.py show --run "<运行记录路径>"
python -B .agents/skills/ascend-op-workflow/scripts/workflow.py verify --run "<运行记录路径>"
```

## 附录：设计评审怎么看

- **成熟源码从哪找。** 先查目标容器里可读的 CANN 源码和已验证工程，包括未发布版本。记下来源、版本或提交、路径和具体分支。缺资料时，再查 CANN 相关算子仓和 vLLM-Ascend。[已有实现调研与复用](../skills/ascend-op-workflow/references/source-reuse.md)
- **能复用到哪一层。** 对比语义、shape、dtype、物理布局、SoC 和调用方式。把 `DESIGN.md` 中的结论落到直接复用、局部适配或借鉴数据流、tiling 与流水，以及各自需要补做的验证。[生成设计评审](../skills/ascend-op-workflow/references/generation-design-review.md)
- **Vector 优化怎么核对。** 看热点卡片的适用性和实际代码。双缓冲要能指出哪些 shape 每核有多个独立 tile、两槽怎样交替、何时预取下一片，以及需要多少 UB。同步要能对应生产者、消费者和槽复用时点。[Vector 方案选型](../skills/ascend-op-workflow/references/vector-patterns.md)
