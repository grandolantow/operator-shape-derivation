# Ascend C 算子 Tiling 设计指南

来源：CANNBot tiling 基础资料与本轮增强的文本快照；仅知识参考，未复制外部插件或执行器。按[读取路由](references/common/reading-routes.md)选择相关章节。许可见仓库 LICENSES/CANN-2.0.txt。

## 根据 shape 和知识选择 tiling

在工作流现有设计阶段完成以下分析，实现阶段沿原实现和代码审查流程落实。本仓生成路线仍为直接 AscendC；外部 CANNBot 的复杂路线另按其原流程执行。所有算子都根据实际 shape 设计 tiling，一个参数化策略可以覆盖全部合法形状。

1. 读取算子原始规格和完整用例信息；存在原始用例备份时以完整备份为准。提取 shape、dtype、stride、布局、属性、广播、归约轴和语义配对。精简 case 只用于调试，不缩小支持域。
2. 按下表选择适用知识。将语义维度整理为独立任务、连续内层、归约长度、复用和尾块；使用目标平台实际资源，文档容量和 shape 示例不作为默认值或实测阈值。
3. 确定可行候选：核数与任务划分、tile/chunk、物理 buffer、workspace、同步及尾块保护都满足资源和精度约束。资源核算见 [资源生命周期](references/common/resource-lifetime.md)。
4. 按实际竞争关系比较访存、有效任务数与波次、复用、转换、启动和准备开销；只展开相关成本。UB 能容纳只证明可行，不证明更快。只有一种合适策略时说明适用条件即可，不凑候选或分支数量。
5. 在原有 DESIGN/PLAN、TileLang 设计或 PERF_DESIGN 中写明形状条件、参数公式、选择理由及不确定性；复杂选型参考 [shape 选型方法](references/common/shape-selection.md)。不新增逐 case 映射、家族表或固定格式交付。
6. 实现时让 Host 公式、launch 参数和 Device 的任务、循环、访存、buffer 及尾块真正一致；在原审查位置核对实际源码。具体核对项见 [shape 选型方法的实现核对](references/common/shape-selection.md#设计与实现核对)。
7. 沿原编译、精度、性能、全量验证和 Trace 流程验证。变更策略时说明原因并同步原设计；旧结果不自动证明新实现通过，结果按实际执行报告。

涉及重排、参数发布、缓存或多阶段 kernel 时，按需读 [运行期开销](references/common/runtime-cost.md)；涉及 API 精度或别名假设时，读 [API 精度注记](references/common/api-precision-notes.md)。融合、门控、旋转及动态量化的语义与候选方向见 [算子模式参考](references/common/operator-patterns.md)，以本算子原始规格为准。

本技能在原设计和审查节点提供知识，不增加执行阶段、额外审核角色、JSON 凭证或编译/编辑门禁。原性能优化自检、精度复验、迭代次数与停止规则保持；本技能不覆盖原工作流的门槛或 Hook。专用类别为空只表示没有该类别清单，不免除通用 shape 和知识分析。默认执行原生成流程；ABC 专项验收由对应实验约定，普通生成不自动追加其重复次数、图或跨流专项测试。

## 算子分类体系

| 类别 | 特征 | 典型算子 | 设计指南 |
|------|------|---------|---------|
| **Reduction 归约类** | 沿轴归约（含索引跟踪变体） | ReduceSum, Softmax, LayerNorm, ArgMax | ✅ [场景路由](references/reduction/patterns.md)（⚠️ 必须先读） / [算法](references/reduction/algorithms.md) |
| **Sort 排序类** | 排序、TopK、外部归并 | Sort, ArgSort, TopK | ✅ [场景路由](references/sort/patterns.md)（⚠️ 必须先读） / [多核两级归并方案](references/sort/alg-two-level-mrgsort.md) |
| **Elementwise 逐元素类** | 输入输出Shape相同，逐元素独立计算 | Sin, Cos, Abs, Exp | ✅ [场景路由](references/elewise/patterns.md)（⚠️ 必须先读） |
| Broadcast 广播类 | 输入Shape不同，需广播对齐 | Add, Mul, Sub | ✅ [场景路由](references/broadcast/patterns.md)（⚠️ 必须先读） |
| Conversion 数据转换类 | 改变布局/形状，合并/拆分张量 | Transpose, Concat, Split | ⚠️ [场景路由](references/conversion/patterns.md)（当前仅 Transpose 部分支持） |
| Random 随机类 | 生成随机数，需种子管理 | RandomUniform, Dropout | 📋 规划中 |
| MatMul 矩阵乘类 | 矩阵乘法，高计算密度，用Cube单元 | MatMul, BatchMatMul, MatMulBias, GroupedMatmul | ✅ [场景路由](references/matmul/patterns.md)（⚠️ 必须先读平台路由） |
| Convolution 卷积类 | 空间卷积，滑动窗口计算 | Conv2D, DepthwiseConv | 📋 规划中 |
| FlashAttention 类 | 注意力计算 | FlashAttention, GQA, MHA, MLA（可叠加量化/稀疏 trait） | ✅ [场景路由](references/flashattention/patterns.md)（⚠️ 必须先读） |
| Pooling 池化类 | 窗口归约与边界访问 | AvgPool, MaxPool | [选型资料](references/pooling/patterns.md)，按原语义核证 |
| NN 神经网络类(其它)| 神经网络专用，多种操作组合 | GroupNorm 等非 attention | 📋 规划中 |

## 通用设计要素（所有类别必须）

以下设计要素是所有算子类别都必须考虑和完成的：

### 1. 多核切分策略

**核心问题**：任务如何分配给多个 AI Core？

**设计要点**：
- 负载均衡：每个核处理的任务量尽量相等
- 数据局部性：相邻数据尽量分配给同一核
- 粒度适中：tile 不能太小（调度开销大），不能太大（并行度低）

**输出**：
- [ ] 总任务切分方式（按哪个维度切）
- [ ] 每个 AI Core 处理的任务量
- [ ] 使用的 AI Core 数量

### 2. UB 切分策略

**核心问题**：单次能处理多少数据？

**设计要点**：
- UB 容量、可用核数和对齐粒度以当前目标平台查询或其官方接口为准；参考示例不作为默认容量
- 单次处理数据量
- 是否需要分 chunk 处理

**输出**：
- [ ] 单次处理的数据量
- [ ] 是否需要分 chunk
- [ ] chunk 大小计算公式

### 3. Buffer 规划

**核心问题**：需要哪些 buffer？各多大？

**设计要点**：
- 输入 buffer（inQueue）
- 输出 buffer（outQueue）
- 中间计算 buffer（tmpBuf, workBuf 等）
- Double Buffer 优化

**输出**：
- [ ] Buffer 列表及用途
- [ ] 各 Buffer 大小计算公式
- [ ] 总 UB 使用量

### 4. 分支场景覆盖

**核心问题**：需要处理哪些不同场景？

**常见分支维度**：
- 数据类型：FP32 / FP16 / BF16 / INT8
- Shape 大小：大 shape / 小 shape
- 数据对齐：32字节对齐 / 非对齐
- 边界情况：最小值 / 最大值 / 特殊值

**输出**：
- [ ] 分支决策条件
- [ ] 各分支的处理策略
- [ ] 边界测试用例
