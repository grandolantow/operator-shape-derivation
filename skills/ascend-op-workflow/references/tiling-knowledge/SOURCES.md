# Tiling 补充卡片的来源与维护

本目录是工作流自有的补充知识；基础类别手册继续从任务固定版本的外部 CANNBot 读取。卡片采用顺序和冲突处理统一见[生成设计评审](../generation-design-review.md#知识来源与策略优先级)。

以下内容压缩改编自 [PR #6](https://github.com/grandolantow/operator-shape-derivation/pull/6) 的固定提交 [`2619c00f74997b7d4b23ae86a77529ddc5ff0416`](https://github.com/lanhongsheng/operator-shape-derivation/tree/2619c00f74997b7d4b23ae86a77529ddc5ff0416)。原路径均位于 `skills/ascend-op-workflow/references/`：

| 本目录卡片 | 原路径与保留内容 |
|---|---|
| [shape-selection.md](shape-selection.md) | `shape-tiling.md`；`tiling-knowledge/references/common/shape-selection.md`、`tiling-knowledge/references/common/operator-patterns.md`；`tiling-knowledge/references/inference/vector-recipes.md`。保留依赖/工作集选型、合行与分段区别、融合和参数化边界。 |
| [resource-lifetime.md](resource-lifetime.md) | `tiling-knowledge/references/common/resource-lifetime.md`。保留物理分配、槽位、字段单位/位宽和核内有效尾段。 |
| [runtime-and-precision.md](runtime-and-precision.md) | `tiling-knowledge/references/common/runtime-cost.md`、`tiling-knowledge/references/common/api-precision-notes.md`。保留准备成本、缓存生命周期、数值假设与证据适用域。 |

原快照声明的上游为 CANNBot `ascendc-tiling-design` 基础资料及增强快照 `experimental_REV5`（2026-11-05）；原文件身份清单见[该提交的来源清单](https://github.com/lanhongsheng/operator-shape-derivation/blob/2619c00f74997b7d4b23ae86a77529ddc5ff0416/docs/SHAPE_TILING_SOURCES.json)。本目录内容已压缩改编，交付字节以本仓提交及安装 manifest 的内容哈希为准，不沿用原文哈希冒充当前卡片身份。

沿用原快照的 CANN Open Software License Agreement 2.0 声明，许可证副本见本仓的 [LICENSES/CANN-2.0.txt](https://github.com/grandolantow/operator-shape-derivation/blob/2601b2f65116f417951d40820411ecdf089d7820/LICENSES/CANN-2.0.txt)；改编不改变原来源的许可范围。固定提交链接在卡片单独安装后仍可定位来源。

卡片不携带原调试轮次、性能倍率或未分发的 SDK 审计材料；其中的方法与例子不表示本轮已完成设备验证。平台/API 事实仍需对照任务目标版本核实。后续修改以本目录为维护源，不从外部整库回拷。
