# Ascend 算子开发工作流

一个独立仓库统一维护算子shape/workload准备、开发编排、合同、执行与归档。由原operator-shape-derivation仓库扩展而来；CANNBot是外部执行依赖。

- **完整入口：** [ascend-op-workflow](skills/ascend-op-workflow/SKILL.md)
- **单独shape/workload：** [operator-shape-derivation](skills/operator-shape-derivation/SKILL.md)
- **安装与使用：** [MindIE / Codex、依赖清单与一键安装提示词](docs/INSTALL.md)；Claude 为选配
- **阶段与分工：** [标准工作流](docs/WORKFLOW.md)
- **MindIE 接入：** [入口、默认 Codex 执行与作业关联](skills/ascend-op-workflow/references/mindie.md)
- **旧入口兼容：** [迁移说明](docs/MIGRATION.md)
- **来源与依赖：** [SOURCES.md](SOURCES.md)

```text
源码/配置/profiling → shape → workload/definition/reference/输入
→ benchmark验证与合同 → 路线核查、成本表与独立设计评审
→ 直接生成首版/复用 → 首次全量正确立即冻结G → 实测性能验收
→ 达标：复核交付G；性能未达标：根因驱动进化 → 最终交付
```

第0～4阶段由Codex完成，包括实现选型与生成；第5～7阶段可由Codex独立或Codex＋Claude协作完成；第8阶段由Codex复核交付。新任务默认 auto：首版全量正确且固定性能目标达标即交付，未达标才进入真实进化。显式 full 保留强制进化范围；历史run不迁移。首版不预设C/V拆分、kernel数量或中间GM布局。

生成直接使用原生 AscendC，默认目标R/G≥1.2；优化目标固定G/O≥1.5，最多5小时有效执行、5轮×5候选。性能预先固定10例、超大不超过3例，正确性保持全量；每轮结束完成慢例及下一步假设分析再继续。G正确且正式计时有效时，生成性能未达标仍可进入进化。用户明确仅生成、仅shape或暂停时服从该范围。安装本仓不会自动启动Claude、NPU任务或定时看护。

实现前执行[生成设计评审](skills/ascend-op-workflow/references/generation-design-review.md)：核对获准组件的支持域、精度与适配成本，列出规约、标量UB访问、同步、DMA粒度等成本，分别评审正确性与性能可行性。`design_check.py`检查当前文件身份及风险回应记录；静态通过不代表实测达标，也不修改外部生成器。

Codex/MindIE 执行所需的[适配脚本和说明](skills/ascend-op-workflow/references/cannbot-execution.md)随 workflow 技能安装，显式连接外部 CANNBot checkout，无需原开发机的独立 adapter 包。新优化任务默认轻量执行，复用有效 G 验收；正 PyTorch 分数低于 1 的兼容、候选预约及适用的全量门禁由本仓维护。MindIE 仍使用原生远端作业与资源工具。

## 快速使用

有两种安装方式：在 MindIE Agent 中复制[安装提示词](docs/INSTALL.md#让-mindie-agent-完成安装)，或在已有源码和任务目录时运行 Python 安装器。安装器需要 Python 3.10+；先预览，再加 `--apply` 写入任务级技能。Windows、Linux 的完整命令和 Claude 选配入口见[安装说明](docs/INSTALL.md)。

默认安装不依赖 CANNBot；生成和优化依赖按[阶段依赖表](docs/INSTALL.md#按阶段准备依赖)核对。仅做 shape 推导可继续使用旧的根目录 SKILL.md，不要求 CANNBot 或 NPU。生成与优化消耗较多 token，建议常规代码模型和中等 effort，复杂问题再局部提升。

## 验证

```bash
python -m unittest discover -s tests -v
python -m unittest discover -s skills/operator-shape-derivation/tests -v
python -m unittest discover -s skills/ascend-op-workflow/scripts -p 'test_*.py' -v
```

适配器的 29 项外部集成测试默认在未指定 CANNBot 时跳过。运行根测试前设置 `CANNBOT_SOURCE_ROOT` 为完整只读 checkout（Bash：`export CANNBOT_SOURCE_ROOT=/path/to/cannbot-skills`；PowerShell：`$env:CANNBOT_SOURCE_ROOT='C:\work\cannbot-skills'`），即可启用真实原生校验、select/refine 和门禁控制逻辑检查；测试中的候选结果为 fixture，不调用 NPU。

测试结果与执行边界见 [VALIDATION.md](VALIDATION.md)。本仓目录名称不参与默认路径推导；可放在任意路径。远端改名状态见迁移说明，不假定尚未完成的改名已生效。

## Shape 驱动 tiling

新生成在原设计阶段完成 shape 分析，并按问题读取相关知识，接入现有实现、审查和验证。见[流程与示例](docs/SHAPE_TILING.md)、[知识入口](skills/ascend-op-workflow/references/tiling-knowledge/INDEX.md)。原直接 AscendC 路线、合同、默认性能集合及优化预算保持不变。

四算子的 A/B/C1 实验结果、逐 shape 数据范围与原流程验收边界见[实验报告](docs/experiments/shape-tiling-abc-20261113.md)。已有设备测量与本次知识发行的离线检查分别记录，不以描述性倍率推断普遍或因果收益。
