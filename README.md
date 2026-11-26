# Ascend 算子开发工作流

**从真实 shape 生成可跑用例，先找成熟实现，再按 shape 设计 tiling、生成和验收 AscendC 算子。** 工作流覆盖 Vector、Cube 和需要 Cube→Vector（C+V 串行）的算子，生成与进化优化复用外部 CANNBot。

[使用说明](docs/USAGE.md) · [安装和依赖](docs/INSTALL.md) · [标准工作流](docs/WORKFLOW.md)

## 这套工作流能做什么

### 从 shape 准备用例

- **从真实调用生成可运行用例。** 结合源码、模型和并行配置及可用的 profiling，推导逻辑 shape、物理布局、有效长度和容量。区分实测覆盖与补充边界，生成可重跑的 workload 和输入。完整工作流接着准备 definition、reference 和 runner，用目标 benchmark 的实际 loader 验证。[Shape 推导](skills/operator-shape-derivation/SKILL.md) · [Benchmark 接入](skills/ascend-op-workflow/references/benchmark.md)

### 设计和生成

- **先找成熟实现，再决定复用范围。** 优先查目标 CANN 环境、容器内可读的源码（含未发布版本）和已验证工程，按需补查 CANN 算子仓与 vLLM-Ascend。对照语义、shape、dtype、布局和目标平台后，选择直接复用、局部适配或借鉴设计。[已有实现调研与复用](skills/ascend-op-workflow/references/source-reuse.md)
- **按 shape 选 tiling。** 按规模、布局和依赖分组，选用通用参数公式或多套 tiling。设计把并行分工、缓冲预算和尾块处理写清楚，并把参数从 Host 传递追到 Kernel 的任务和循环。[Shape 到 tiling](skills/ascend-op-workflow/references/shape-tiling.md) · [知识路由](skills/ascend-op-workflow/references/tiling-reading-routes.md)
- **首版落实适用的 Vector 优化。** 按算子和 SoC 读 CANNBot 的高频卡片，逐项判断尾块搬运、双缓冲、参数驻留、批量 DMA 等方案。条件满足时在首版实现，代码检视核对实际分支、预取和同步。[Vector 方案选型](skills/ascend-op-workflow/references/vector-patterns.md)
- **支持按需采用 Cube→Vector 串行。** 评估中间数据的 GM 读写和布局转换成本，再确定 C、V 各自的复用或生成方案及接口。独立验证 C、用参考中间结果验证 V，再对完整组合做全量精度和性能验证。优化共用父任务预算。[C→V 串行](skills/ascend-op-workflow/references/cv-serial.md)
- **写代码前评审具体成本。** 在 `DESIGN` 中核对组件支持域、精度、规约次数、标量 UB 访问、DMA 粒度和同步依赖。独立走读分别检查正确性和性能可行性，主要数据通路或操作粒度变更后复审。[生成设计评审](skills/ascend-op-workflow/references/generation-design-review.md)

### 验收和优化

- **冻结首个正确版本，统一性能对比。** 直接生成或复用 AscendC，首个全量正确版本冻结为 `G`。新建正式任务全量验精度，提前冻结 10 个性能用例，最多 3 个超大用例。首版比原实现 `R`，优化候选 `O` 始终比冻结的 `G`，报告逐例耗时和退化。[性能集合与逐轮分析](skills/ascend-op-workflow/references/performance-and-round-review.md)
- **首版达标就交付，按需做轻量优化。** 默认 `auto` 在正式验收未达标且具备条件时进入优化，复用有效的 `G` 验收。每轮根据慢例、变更机制和可验证的假设选择下一批候选。也可指定 `generation_only` 或 `full`。[连续推进与停止](skills/ascend-op-workflow/references/continuation.md)
- **按原任务续跑，支持隔离 A/B。** 归档合同、源码、构建与库、作业和原始结果，恢复时沿用原基线和剩余预算。需要比较生成流程时，两路从同一需求独立起跑，冻结代码后同卡同例对比，分别报告生成耗时与 kernel 性能。[归档与交接](skills/ascend-op-workflow/references/protocol.md) · [生成阶段对照](skills/ascend-op-workflow/references/generation-comparison.md)

默认首版目标为 `R/G ≥ 1.2`，优化目标为 `G/O ≥ 1.5`，均按逐例加速比的几何平均计算。优化默认最多累计活跃 5 小时、5 轮、每轮 5 个候选。实际验收按任务合同执行。

## 快速使用

有两种安装方式：在 MindIE Agent 中复制[安装提示词](docs/INSTALL.md#让-mindie-agent-完成安装)，或在已有源码和任务目录时运行 Python 安装器。安装器需要 Python 3.10+；先预览，再加 `--apply` 写入任务级技能。Windows、Linux 的完整命令和 Claude 选配入口见[安装说明](docs/INSTALL.md)。

默认安装配套准备 CANNBot 官方主线 `master` 的源码和技能，并记录实际版本。只需要 workflow 和 shape 时，可使用 `--workflow-only`。各阶段的运行依赖见[安装说明](docs/INSTALL.md#按阶段准备依赖)。仅做 shape 推导可继续使用旧的根目录 SKILL.md，不要求 CANNBot 或 NPU。生成与优化消耗较多 token，建议常规代码模型和中等 effort，复杂问题再局部提升。

### 执行入口

- [ascend-op-workflow 主入口](skills/ascend-op-workflow/SKILL.md) · [独立 shape/workload 技能](skills/operator-shape-derivation/SKILL.md)
- [MindIE 接入与远端作业关联](skills/ascend-op-workflow/references/mindie.md) · [CANNBot 执行适配](skills/ascend-op-workflow/references/cannbot-execution.md)
- [旧入口兼容与迁移](docs/MIGRATION.md) · [来源与依赖](SOURCES.md)

默认由 Codex 执行，Claude 协作为选配。执行适配脚本随技能安装，使用显式指定的 CANNBot checkout。安装技能本身只准备任务级文件。

## 验证

```bash
python -m unittest discover -s tests -v
python -m unittest discover -s skills/operator-shape-derivation/tests -v
python -m unittest discover -s skills/ascend-op-workflow/scripts -p 'test_*.py' -v
```

适配器的 29 项外部集成测试默认在未指定 CANNBot 时跳过。运行根测试前设置 `CANNBOT_SOURCE_ROOT` 为完整只读 checkout（Bash：`export CANNBOT_SOURCE_ROOT=/path/to/cannbot-skills`；PowerShell：`$env:CANNBOT_SOURCE_ROOT='C:\work\cannbot-skills'`），即可启用真实原生校验、select/refine 和门禁控制逻辑检查；测试中的候选结果为 fixture，不调用 NPU。

测试结果与执行边界见 [VALIDATION.md](VALIDATION.md)。本仓目录名称不参与默认路径推导；可放在任意路径。远端改名状态见迁移说明，不假定尚未完成的改名已生效。
