# 按问题读取 Tiling 知识

先读本工作流命中的正文，再用任务固定版本的 CANNBot 补全。设计理念、选型、调度偏好和示例阈值冲突时优先本工作流；平台/SDK 支持域、算子语义及冻结合同仍须成立，具体规则只在[生成设计评审](../generation-design-review.md#知识来源与策略优先级)维护。无需通读整库，也不能只引用资料名而不读相关正文。

| 当前问题 | 本地正文 | 基础知识与补充 |
|---|---|---|
| 从 shape、dtype、stride 和依赖选择 tiling | [Shape 选型](common/shape-selection.md)、[物理资源](common/resource-lifetime.md) | 一个参数化策略可覆盖多个 shape；结构差异足够时才分流。 |
| 独立逐元素 | [场景路由](elewise/patterns.md)、[完整参数与预算](elewise/tiling.md) | 字节单位、逐 buffer 对齐、混合 dtype 示例优先于外部旧公式。 |
| 广播、布局变换 | [算子模式](common/operator-patterns.md) | 基础 [Broadcast](https://gitcode.com/chenshushu2020/cannbot-skills/blob/bcb8067bd6ebab19e490b317ad8250e25a18316b/ops/ascendc-tiling-design/references/broadcast/patterns.md)、[Conversion](https://gitcode.com/chenshushu2020/cannbot-skills/blob/bcb8067bd6ebab19e490b317ad8250e25a18316b/ops/ascendc-tiling-design/references/conversion/patterns.md)。 |
| 归约、归一化、融合 | [归约路由](reduction/patterns.md)、[全载](reduction/ar-fullload.md)、[核内分段](reduction/ar-colsplit.md) | 短行读 [Merge-row](reduction/ar-merge-row.md)，融合读 [Norm](reduction/norm-fusion.md)；基础 [Welford](https://gitcode.com/chenshushu2020/cannbot-skills/blob/bcb8067bd6ebab19e490b317ad8250e25a18316b/ops/ascendc-tiling-design/references/reduction/alg-welford.md)、[跨核归约](https://gitcode.com/chenshushu2020/cannbot-skills/blob/bcb8067bd6ebab19e490b317ad8250e25a18316b/ops/ascendc-tiling-design/references/reduction/alg-group-reduce.md)、[二分累加](https://gitcode.com/chenshushu2020/cannbot-skills/blob/bcb8067bd6ebab19e490b317ad8250e25a18316b/ops/ascendc-tiling-design/references/reduction/alg-dichotomy.md)。 |
| 排序、TopK、带索引归约 | [API/精度限定](common/api-precision-notes.md)、[归并边界](sort/merge-boundaries.md) | 先读本地限定，再读基础 [Sort](https://gitcode.com/chenshushu2020/cannbot-skills/blob/bcb8067bd6ebab19e490b317ad8250e25a18316b/ops/ascendc-tiling-design/references/sort/patterns.md)、[两级归并](https://gitcode.com/chenshushu2020/cannbot-skills/blob/bcb8067bd6ebab19e490b317ad8250e25a18316b/ops/ascendc-tiling-design/references/sort/alg-two-level-mrgsort.md)、[With-index](https://gitcode.com/chenshushu2020/cannbot-skills/blob/bcb8067bd6ebab19e490b317ad8250e25a18316b/ops/ascendc-tiling-design/references/reduction/with-index.md)。 |
| Pooling 与窗口访问 | [Pooling 选型](pooling/patterns.md) | 布局地址、输出窗口、padding、UB 和重叠读取；不套用整行归约语义。 |
| MatMul / Attention | [资源口径](common/resource-lifetime.md) | 基础 [MatMul](https://gitcode.com/chenshushu2020/cannbot-skills/blob/bcb8067bd6ebab19e490b317ad8250e25a18316b/ops/ascendc-tiling-design/references/matmul/patterns.md)、[FlashAttention](https://gitcode.com/chenshushu2020/cannbot-skills/blob/bcb8067bd6ebab19e490b317ad8250e25a18316b/ops/ascendc-tiling-design/references/flashattention/patterns.md)，按目标架构进入适用方案。 |
| 多阶段、参数发布、缓存、Host 准备 | [运行期开销](common/runtime-cost.md) | 分开冷启动、eager、捕获/重放和 kernel/Host/端到端口径。 |
| API、近似数学、累加与别名 | [API 精度注记](common/api-precision-notes.md) | 保留版本支持域、反例与未知项；不以另一 dtype 通过排除共享原因。 |
| 推理中的配对、门控、量化等组合 | [六类切分与案例](inference/vector-recipes.md)、[十类推理场景](inference/inference-routes.md)、[算子模式](common/operator-patterns.md) | [AddRmsNorm 的 key/参数](inference/add-rmsnorm-keys.md)、[十二样本源码观察](inference/vector-source-evidence.md)。 |
| Index / Scatter / 分桶冲突 | [算子模式](common/operator-patterns.md)、[Shape 选型](common/shape-selection.md) | 当前快照没有专项手册，查任务 checkout 的目标代际路由；缺失时记具体缺口，不能用 Sort 代替。 |

合成 shape、容量、对齐和调度 key 均只在各自示例范围使用，不是通用派发阈值。设计取舍和 Host/Kernel 参数映射写入原 DESIGN；执行、评审和验收沿用工作流，不在知识入口再列一套步骤。

[来源与去向](SOURCES.md)逐项记录原 55 份文档、本地增强、混合正文的保留位置和 32 份已核对重复资料的固定版本及哈希。
