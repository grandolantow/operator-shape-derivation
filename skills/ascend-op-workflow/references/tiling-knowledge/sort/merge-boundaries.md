# 排序与 TopK：API 限定及归并边界

基础排序方案见固定 CANNBot 的 `references/sort/patterns.md` 与 `alg-two-level-mrgsort.md`，确认为重复的正文由[来源表](../SOURCES.md)定位。本卡保留本地 API 限定，并明确按参考方案实现时的长度、同步和容量条件；这些约束优先于参考文档中的简化示例。

## 类型转换与容量

输入为 fp32 时，是否省略 Cast/转换 buffer 取决于消费者和物理生命周期，不能理解成同 dtype Cast 自动完成拷贝。Extract 后 Cast 回目标 dtype，独立输出 buffer 是保守账本选择，别名能力按目标重载核实，见 [API 精度注记](../common/api-precision-notes.md)。这是原 PR 两份 Sort 资料的增强内容。

tile 上限按输入、转换、索引、proposal、API scratch 及各自物理份数逐项对齐求解；scratch 用目标 SDK 支持的查询或定义。`tileSize=4096` 是示例，不是通用最优值。多级核内/跨核归并是候选组织，是否采用取决于实际可用 API、数据规模、同步和流量成本。

## 每路有效长度与 TopK 截断

各局部分区须采用与最终结果一致的比较顺序，含相同值、NaN 和稳定索引规则。每个分区保留前 K 后再归并，不表示某一批的前 K 已包含全局答案。每次归并以真实路长计算：

```text
inputLen[i] = min(actualRunLen[i], K)  # 不存在的路长度为 0
total = Σ inputLen[i]
outputLen = min(K, total)
stopThreshold = total - outputLen    # 以此语义作推导，实际 API 参数含义另核
```

不能把所有路长都写成 K 或 currentElements；尾路不足 K 时会读入无效数据。归并后更新输出路的真实长度，容量与尾块都由它推导。

## 工作区与同步

每路元数据包含实际 workspace 半区、偏移和有效长度。例如 4 路归并时，两个核分别有 5/4 个初始 tile，局部需 2/1 轮，最终可能落在不同半区。可明确选择每路携带位置，或统一轮数并让提前完成的核直通复制；不能共享一个未经证明的最终 flag。

双半区的一个容量模型为：

```text
coreStrideBytes = align_up(E_c * proposalBytes, alignment)
halfBytes = usedCore * coreStrideBytes
totalBytes = 2 * halfBytes
```

这是固定槽位的示例。各组读写必须证明 `offset + actualBytes <= halfBytes`，并避免覆盖尚未消费的路；不能仅靠起始偏移或 `K*M*2` 保证安全。改变半区、路长或布局后同步更新基址与容量证明。

区分实际 launch 数、非空核数和屏障参与集合。SyncAll 涉及的全部已启动参与核按相同轮序到达；无任务核跳过 GM 访问但不能提前返回或跳过屏障。最终仅 Core 0 计算时，末屏障仍按参与集合执行。Reset/缓冲复用前完成相关异步访问并核目标 SDK 语义；队列深度逐物理槽计入预算。

来源与维护：[就近来源清单](../SOURCES.md)。API 限定来自原 PR6 Sort 两卡；本卡对恢复知识的长度、工作区及同步边界作静态审查澄清，未新增设备实验或性能结论。
