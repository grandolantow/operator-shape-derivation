# Ascend 算子开发工作流

一个独立仓库统一维护算子shape/workload准备、开发编排、合同、执行与归档。由原operator-shape-derivation仓库扩展而来；CANNBot是外部执行依赖。

- **完整入口：** [ascend-op-workflow](skills/ascend-op-workflow/SKILL.md)
- **单独shape/workload：** [operator-shape-derivation](skills/operator-shape-derivation/SKILL.md)
- **安装与使用：** [Windows Codex / Linux Claude](docs/INSTALL.md)
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

## 快速使用

先准备本仓，再创建独立任务目录。默认安装不依赖 CANNBot；实际生成/优化需要时再询问安装或复用已有 checkout。Windows示例：

```powershell
python .\install_codex.py --task-dir C:\work\tasks\my-op
python .\install_codex.py --task-dir C:\work\tasks\my-op --apply
```

Linux Codex 使用同一个 Python 安装器。Claude 选配入口：

```bash
bash ./install-claude.sh --cannbot-root /workspace/cannbot-skills --task-dir /workspace/tasks/my-op
bash ./install-claude.sh --cannbot-root /workspace/cannbot-skills --task-dir /workspace/tasks/my-op --apply
```

以上任务目录须已存在。第一条预览，第二条实际安装；未知配置或已修改的托管内容不会被覆盖。打开任务目录并使用ascend-op-workflow；Claude执行仅在明确选择协作/Claude入口时需要。

仅做shape推导可继续使用旧的根目录SKILL.md安装方式，不要求CANNBot或NPU。生成与多轮优化消耗较多 token，建议常规代码模型和中等 effort，复杂问题再局部提升；CANNBot 保持独立且不修改。实际依赖和更新注意事项见安装说明。

## 验证

```bash
python -m unittest discover -s tests -v
python -m unittest discover -s skills/operator-shape-derivation/tests -v
python -m unittest discover -s skills/ascend-op-workflow/scripts -p 'test_*.py' -v
```

测试结果与执行边界见 [VALIDATION.md](VALIDATION.md)。本仓目录名称不参与默认路径推导；可放在任意路径。远端改名状态见迁移说明，不假定尚未完成的改名已生效。
