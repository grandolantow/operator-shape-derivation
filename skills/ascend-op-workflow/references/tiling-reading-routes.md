# 按算子家族与执行策略读取知识

先从冻结规格识别语义、shape、dtype、布局/stride 和依赖，再组合下面两个维度。按语义定位，不要求名称在表内；括号内仅为示例，不是支持名单。只读当前决策需要的正文，文件名和索引不代替正文。

基础算法仍使用任务固定的外部 CANNBot checkout，入口 `ops/ascendc-tiling-design/SKILL.md`。下列外部 `references/...` 均相对此技能目录；曾核版本为 `affd5a88dd956022a598adf2f5ed9f3e26718d48`，其他版本从实际入口定位，不强制升级或复制基础库。外部类别名不是可执行API支持声明。

## 维度一：算子家族与语义

| 家族/语义（示例） | 应读正文与解决的问题 | 基础资料及不可省略的条件 |
|---|---|---|
| 独立逐元素（激活、算术、比较） | [逐元素预算](tiling/elementwise-budget.md)、[Vector策略](tiling/vector-recipes.md)：混合dtype容量、有效tile和分工 | `references/elewise/patterns.md`、`tiling.md`；Flatten须证明布局与输出独立 |
| 广播、配对/门控、量化（Bias、RoPE） | [语义与复用](tiling/operator-patterns.md)：广播轴、配对地址、统计组、融合顺序 | `references/broadcast/patterns.md`及对应算法；广播不是重复独立输入，量化不跨组 |
| 归约、分段归约（Sum、Max、Softmax统计） | [归约预算](tiling/reduction-budget.md)：完整统计域、全载/分段与输出；输出再用统计量时组合下一行 | `references/reduction/patterns.md`及实际算法；段边界、累积精度、合并顺序按原语义 |
| 统计后逐元素输出/融合（Norm、Softmax） | [统计与数据流](tiling/norm-fusion.md)：保留/重读/重算；Norm公式仅用于适用语义 | 外部归约及适用的稳定统计算法；不能把Norm公式套给Softmax或其他统计函数 |
| 前缀/递推（Scan、CumSum） | [Vector策略](tiling/vector-recipes.md)、[API精度](tiling/api-precision.md)、[运行成本](tiling/runtime-cost.md)：依赖、精度与阶段成本 | 从实际基础入口定位扫描算法；inclusive/exclusive、方向、段边界及块间进位须单独证明，独立行归约不能替代扫描 |
| 桶统计、冲突累加（Histogram、计数） | [Vector策略](tiling/vector-recipes.md)、[资源账本](tiling/resource-lifetime.md)、[运行成本](tiling/runtime-cost.md)：输入分块、局部统计和归并 | 原桶边界/异常值/计数语义；核原子/冲突处理支持，不把桶数当连续行归约长度 |
| 窗口归约（Pooling） | [窗口路由](tiling/pooling.md)：真实布局、窗口重叠复用、padding/分母及输出映射 | 原窗口规格；有dilation按采样地址求重叠，不能直接套独立行Merge-row |
| 邻域采样/加权输出（Resize、Interpolate） | [地址与复用](tiling/operator-patterns.md)、[Vector策略](tiling/vector-recipes.md)、[API精度](tiling/api-precision.md)：输出分工、邻域复用和Gather域 | 原mode、坐标变换、权重、边界；Pooling只在地址重叠分析适用时参考，不能继承其归约公式 |
| 排序、选择（Sort、TopK） | [API精度](tiling/api-precision.md)、[资源账本](tiling/resource-lifetime.md)、[运行成本](tiling/runtime-cost.md)：索引表示、临时量和多轮合并 | `references/sort/`；稳定性、相等值顺序、NaN及索引语义以原合同为准 |
| 索引读取/更新（Gather、Scatter、Embedding） | [Vector策略](tiling/vector-recipes.md)、[资源账本](tiling/resource-lifetime.md)、[API精度](tiling/api-precision.md)：地址域、工作区、冲突 | `references/index/`（A2/A3）、`scatter/`（A5）；核目标平台与边界/重复索引语义，不默认写入互不重叠 |
| 布局转换/重排（Transpose、Pack） | [Vector策略](tiling/vector-recipes.md)、[运行成本](tiling/runtime-cost.md)：源/目标连续维、搬运和重排代价 | `references/conversion/`；证明双向地址映射与尾段，不把逻辑reshape等同物理连续 |
| 矩阵/张量收缩（MatMul、卷积映射） | [资源账本](tiling/resource-lifetime.md)、[运行成本](tiling/runtime-cost.md)：资源层级、准备与融合成本 | `references/matmul/`及实际卷积资料；Cube布局/多级存储另核，Vector的UB公式不能替代完整分块模型 |
| 复合数据流（Attention等） | [推理场景](tiling/inference-routes.md)、[运行成本](tiling/runtime-cost.md)，按阶段组合归约/矩阵等入口 | `references/flashattention/`及实际基础资料；因果mask、变长、精度和阶段依赖按原语义，不因命中家族就宣称支持完整API |

## 维度二：可组合的执行策略

| 决策/条件 | 应读正文 | 与家族的组合边界 |
|---|---|---|
| Flatten、按行/列分工、二维切分 | [Vector策略](tiling/vector-recipes.md) | 先证明输出独立和布局条件；核内分段不自动增加核间任务 |
| 整行驻留、核内分段或跨块合并 | [归约预算](tiling/reduction-budget.md)、[运行成本](tiling/runtime-cost.md) | 仅在对应归约语义适用时用预算公式；扫描另计进位，跨块合并另计工作区/同步 |
| 短行很多，多行合并 | [Merge-row](tiling/ar-merge-row.md) | 独立行归约及Norm可评估；只合并搬运与调度，不跨行统计 |
| 统计后保留、重读、重算 | [统计数据流](tiling/norm-fusion.md#二中间阶段可组合的成本候选) | 按实际输入/中间/输出代入；重算所需原输入丢弃时仍计重读 |
| 邻域/参数复用、窗口块驻留 | [Pooling候选](tiling/pooling.md#二候选切分layout-aware连续维优先)、[语义与复用](tiling/operator-patterns.md) | 按真实地址重叠计算；窗口归约、采样加权的计算语义分开 |
| 非连续访存、Gather、重排 | [Vector策略](tiling/vector-recipes.md)、[API精度](tiling/api-precision.md)、[运行成本](tiling/runtime-cost.md) | 计索引准备、地址范围、有效访问、重排与复用；批量调用不保证连续访问或收益 |
| 冲突更新、局部聚合再归并 | [资源账本](tiling/resource-lifetime.md)、[API精度](tiling/api-precision.md)、[运行成本](tiling/runtime-cost.md) | 先读家族基础算法；证明原子/归并语义及顺序，计局部缓冲、合并和同步，不预设通用算法 |
| 双缓冲、尾块、参数驻留、RegBase | [已有Vector路由](vector-patterns.md)、[资源账本](tiling/resource-lifetime.md) | 保留原performance-best-practices正文；结合实际槽位、依赖和目标架构 |

例如短行Norm组合“统计输出家族＋多行合并”，但Merge-row标量输出预算不能替代整行输出。Transpose组合“布局转换＋二维切分/重排”；Scan组合“前缀依赖＋分段/跨块”，必须另证进位，不能照搬独立归约。

## 公共约束：只维护一份规则

| 公共问题 | 统一正文 | 家族/策略卡保留什么 |
|---|---|---|
| UB字节、对齐、copies、物理生命周期、同步容量、长度与偏移 | [物理资源账本](tiling/resource-lifetime.md) | 场景代入项、参数公式、算例及特有边界，不重述公共规则 |
| Cast、别名、累积/舍入、排序索引精度 | [API与精度](tiling/api-precision.md) | 原语义决定的统计域、epsilon、padding等仍在对应家族 |
| 多阶段、准备/重排、缓存与计时范围 | [运行期开销](tiling/runtime-cost.md) | 实际访问次数、工作区、同步及启动代价 |

## 未命中、复合算子与原流程落实

- 名称未列出时，先拆出地址映射、统计/递推/冲突依赖和复用关系，再组合家族与策略；复合算子同时阅读相关入口，不强行塞入单一分类。
- 没有匹配算法正文时，从任务固定的基础技能入口检索实际语义与目标架构资料，再读公共约束；资料仍缺就在原DESIGN记录具体缺项，不编造专用卡片、API支持或套用不成立的公式。
- 推理shape与prefill/decode映射读[推理场景表](tiling/inference-routes.md)；kernel key与参数边界读[AddRmsNorm示例](tiling/add-rmsnorm-keys.md)；追溯源码读[样本观察](tiling/source-observations.md)。示例不是通用阈值。
- 架构、SDK、dtype不匹配的方案不照搬。阅读后在原DESIGN已有适用性表说明：语义、策略条件、正文版本/章节、参数与备选取舍，不新增模板、JSON字段或阅读监控。
- 原走读核依据，开发按同一引用实现，原代码检视核host/launch/kernel消费位置；原精度和同版性能不变。见[短指南](shape-tiling.md)及[来源说明](../../../SOURCES.md#shape-tiling-增量知识来源)。

审核与使用时，策略条件/反例/代表shape读Vector策略原表，广播/配对读语义卡及地址例；公共约束只在资源、API和运行成本正文维护。路由覆盖不等于所有家族都有新增专用知识或已完成设备验证。
