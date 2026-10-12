# Ascend 算子开发工作流

一个独立仓库统一维护算子shape/workload准备、开发编排、合同、执行与归档。由原operator-shape-derivation仓库扩展而来；CANNBot是外部执行依赖。

- **完整入口：** [ascend-op-workflow](skills/ascend-op-workflow/SKILL.md)
- **单独shape/workload：** [operator-shape-derivation](skills/operator-shape-derivation/SKILL.md)
- **安装与使用：** [Windows Codex / Linux Claude](docs/INSTALL.md)
- **阶段与分工：** [标准工作流](docs/WORKFLOW.md)
- **旧入口兼容：** [迁移说明](docs/MIGRATION.md)
- **来源与依赖：** [SOURCES.md](SOURCES.md)

```text
源码/配置/profiling → shape → workload/definition/reference/输入
→ benchmark验证与合同 → 实现选型及生成 → 全量验收并固定G
→ 实际进化优化 → 最终复核、源码/数据/复现说明交付
```

第0～4阶段由Codex完成，包括实现选型与生成；第5～7阶段可由Codex独立或Codex＋Claude协作完成；第8阶段由Codex复核交付。完整任务在合格G冻结后连续进入真实进化，不在HANDOFF文件处结束。

默认生成目标R/G≥1.2；优化目标固定G/O≥1.5，最多5轮×5候选。G正确且正式计时有效时，生成性能未达标仍可进入进化。用户明确仅生成、仅shape或暂停时服从该范围。安装本仓不会自动启动Claude、NPU任务或定时看护。

## 快速使用

先准备本仓和完整外部CANNBot checkout，再创建独立任务目录。Windows示例：

```powershell
python .\install_codex.py --cannbot-root C:\work\cannbot-skills --task-dir C:\work\tasks\my-op
python .\install_codex.py --cannbot-root C:\work\cannbot-skills --task-dir C:\work\tasks\my-op --apply
```

Linux协作入口：

```bash
bash ./install-claude.sh --cannbot-root /workspace/cannbot-skills --task-dir /workspace/tasks/my-op
bash ./install-claude.sh --cannbot-root /workspace/cannbot-skills --task-dir /workspace/tasks/my-op --apply
```

以上任务目录须已存在。第一条预览，第二条实际安装；未知配置或已修改的托管内容不会被覆盖。打开任务目录并使用ascend-op-workflow；Claude执行仅在明确选择协作/Claude入口时需要。

仅做shape推导可继续使用旧的根目录SKILL.md安装方式，不要求CANNBot或NPU；完整安装才需要外部依赖。实际依赖和更新注意事项见安装说明。

## 验证

```bash
python -m unittest discover -s tests -v
python -m unittest discover -s skills/operator-shape-derivation/tests -v
python -m unittest discover -s skills/ascend-op-workflow/scripts -p test_workflow.py -v
```

测试结果与执行边界见 [VALIDATION.md](VALIDATION.md)。本仓目录名称不参与默认路径推导；可放在任意路径。远端改名状态见迁移说明，不假定尚未完成的改名已生效。
