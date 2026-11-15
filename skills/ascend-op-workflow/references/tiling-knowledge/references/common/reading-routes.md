# 按问题读取 tiling 知识

新生成先从原规格与完整 shape 集合识别语义、dtype、布局、连续轴、独立任务和尾块，再选择相关资料。类别入口读完整命中的场景；算法细节只读选入或需要排除的方案。不能只列资料名、不打开正文就开始照经验生成，也不要求通读整个知识库。

| 当前决策或问题 | 先读 | 条件性补读及使用位置 |
|---|---|---|
| 所有新生成的 shape→参数设计 | [shape 选型](shape-selection.md)、[资源生命周期](resource-lifetime.md) | 原设计中说明适用域、参数公式、实际资源预算和取舍；一个参数化策略也可以覆盖所有 shape |
| 独立逐元素 / 广播 | [逐元素场景](../elewise/patterns.md) / [广播场景](../broadcast/patterns.md) | 连续性、广播 stride、升精度缓冲、核内有效尾块；不自动展平所有输入 |
| 归约、归一化与融合 | [归约场景](../reduction/patterns.md) | 按行/合行/核内 Split-D/跨核合并分别比较；融合读 [norm-fusion](../reduction/norm-fusion.md)，短行读 [merge-row](../reduction/ar-merge-row.md) |
| 排序 / TopK | [排序场景](../sort/patterns.md) | 比较实际可用算法，核算排序、串行依赖与合并 |
| 分桶、索引访问与冲突更新 | 本快照未包含 Index/Scatter 专项；从实际外部 CANNBot checkout 的 `ascendc-tiling-design` 读取目标代际对应的 Index / Scatter 路由，并核当前 SDK 能力 | 仅选入排序方案时再读排序场景；结合 [shape 选型](shape-selection.md)核算唯一写者、重扫和同步。外部专项资料缺失时报告具体缺口，不用 Sort 代替 |
| 布局变换 / 池化 | [变换场景](../conversion/patterns.md) / [池化选型](../pooling/patterns.md) | 非连续访问、邻域重读、窗口和 padding 语义 |
| MatMul / Attention | [MatMul 场景](../matmul/patterns.md) / [Attention 场景](../flashattention/patterns.md) | 按目标架构进入实际可用方案，不把 Vector 的 UB 示例套用到 Cube |
| 多阶段、参数发布、缓存、host 准备 | [运行期开销](runtime-cost.md) | 区分冷启动、eager、图捕获/重放及 kernel / host / 端到端口径 |
| Cast、近似、归约累加、别名等精度假设 | [API 精度注记](api-precision-notes.md) | 再核当前 SDK 官方约束；材料中的假设不能替代原精度验证或改容差 |
| 推理中的门控、旋转、量化等组合 | [算子模式](operator-patterns.md) | [六类基础切分](../inference/vector-recipes.md)、[推理选型](../inference/inference-routes.md)、[AddRmsNorm](../inference/add-rmsnorm-keys.md)、[源码观察边界](../inference/vector-source-evidence.md) |

读取之后，在原 DESIGN / PLAN / PERF_DESIGN 或现有评审材料中写明采用的资料、适用条件、选择及未采用的相关方案理由。可链接路径或章节并记录版本；已有工具能记录实际读取时保留原记录，缺失时写未知。原审查者核知识与当前 shape 是否匹配、参数是否在 host/kernel 中真正消费；不增加一份必填 JSON、新的阶段或新的验收角色。

实现后沿原流程编译、精度与性能验证。资源可行、数值正确与性能改善分别下结论；没有改善的候选不能替代已有有效基线。新规则只用于接续后的真实活动，不倒填历史阅读或通过记录。ABC 专项中 A 仍使用冻结的自然基线，B / C1 才读取获准增强资料；不得为了补读知识而重生成已冻结的 A 或混入另一臂实现。
