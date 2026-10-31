# 标准工作流

| 阶段 | 负责人 | 交付 |
|---|---|---|
| 0 需求接收 | Codex | 源码、范围、环境、执行方式、停点 |
| 1 shape推导 | Codex | 张量关系、来源、动态轴、有效区与物理布局 |
| 2 benchmark | Codex | workload、definition、reference、输入构造、真实loader验证 |
| 3 合同 | Codex | 全量正确性case、固定10例性能集（超大≤3）、oracle、R、精度、计时、资源、预算与hash |
| 4 选型与生成 | Codex | 路线核查、操作粒度成本表、独立可行性评审；直接生成或复用，首次全量正确立即冻结G |
| 5 轻量验收与G | Codex独立 / Codex＋Claude | 全量正确性、固定10例正式计时、源码/库一致；auto达标交付G，未达标优化 |
| 6 进入进化 | 同第5阶段所选模式 | auto性能未达标或显式full时实际调用ops-perf-evolution |
| 7 进化搜索 | 同第5阶段所选模式 | 固定G，最多5小时有效执行、5轮×5候选，逐轮分析后继续 |
| 8 交付 | Codex | 全量复核、逐case结果、最佳正确版本、原始日志和复现命令 |

完整规范只有一份：[主skill](../skills/ascend-op-workflow/SKILL.md)。本页用于导航，不另设协议。

- [C→V串行](../skills/ascend-op-workflow/references/cv-serial.md)：先找成熟C/V，根据shape/workload筛选实现，再冻结内部边界；独立C、oracle输入的V、完整组合分别验证，共享父预算。
- [生成设计评审](../skills/ascend-op-workflow/references/generation-design-review.md)：实现前核查支持域、成本与风险回应；结构或操作粒度实质变化需复审，静态检查不替代实测。
- [连续推进与停止](../skills/ascend-op-workflow/references/continuation.md)：auto首版验收达标交付G、未达标进入进化；内部score不等于正式G/O；恢复不重置预算；用户暂停优先。
- [CANNBot 执行适配](../skills/ascend-op-workflow/references/cannbot-execution.md)：四个内置脚本随技能安装，指定只读 checkout；默认轻量优化，已有 native 保持原模式。
- [执行模式](../skills/ascend-op-workflow/references/execution-modes.md)：Codex独立无需Claude；协作模式核实原会话与进程，避免重复派发。
- [benchmark](../skills/ascend-op-workflow/references/benchmark.md)：shape技能不默认补definition/reference，主工作流接续完成完整数据包。
- [任务模板](../skills/ascend-op-workflow/references/task-template.md)、[合同](../skills/ascend-op-workflow/references/operator-contract.md)、[归档](../skills/ascend-op-workflow/references/protocol.md)。

每个算子只用一个父任务目录与状态入口，形状、合同、生成、优化、证据和交付按阶段归档。所有实际source/build/库/测量记录关联同一合同与case集合。环境与设备配置从当前任务发现，不把历史IP、代理、设备号和资源阈值写成全局规则。
