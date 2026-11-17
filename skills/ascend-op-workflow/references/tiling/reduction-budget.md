# 归约：全载、分段与完整统计域

输入归一化为 `[A₁,R,A₀]`。尾轴 AR 为 `A₀=1`，独立行数 M=A₁；非尾轴 ARA 保留连续 A₀ 切片并从外部归约主路由读取对应算法。本文只提取原 FullLoad/ColSplit/patterns 的增强部分。

## 全载可行性

一行完整工作集要包含输入槽位、输出、独立统计、升精度临时量、参数驻留和实际 Reduce API scratch：

```text
c*align_up(R*e,a) + outputBytes + statsBytes(R)
  + tmpBytes(R) + reserveBytes ≤ U
```

只有非输入项独立于 R（或取覆盖候选的保守上界）、e 整除 a 时，才可用闭式：

```text
Rmax = floor((U-outputBytes-statsBytes-tmpBytes-reserveBytes)/(c*a))*(a/e)
```

存在整行 FP32 中间时，stats/temporary 可能随 R 变化，回到定义式求解。不能只用 `R*输入dtype` 判断整行可驻留。全载是“单任务完整归约域驻留”，不是整个 tensor 全载。

## 核内分段

全载不可行时，先列本分支的真实物理分配。在非输入项不随 chunk 变化（或已有保守上界）的假设下：

```text
B = U-reserveBytes-statsBytes-tmpBytes-scalarBuffersBytes
C = min(floor(B/(copies*a))*(a/e), R)   # e整除a，所有项采用byte
numChunks = ceil_div(R,C)              # C>0
lastChunk = R-(numChunks-1)*C
```

输出队列、chunk 结果和统计若是独立槽位须全部计入；同槽合法复用只计一次。C clamp 到未对齐 R 后，实际分配仍按字节对齐。临时量随 C 变化时用完整不等式重新求解。`R>C` 只说明该分支需要分段，不能反证所有全载组织都不可行。

合成核算：`U=100000,reserve=1000,stats=128,tmp=4000,scalar=64,copies=2,e=4,a=32`，B=94808，C上限11848；总占用99976B。下一对齐档11856会用100040B。R=50000时5段，末段2608元素。

核间仍按行分工；同核循环拆 R 不增加独立行任务。行数少且单行重时，跨核拆行是另一个候选，须另计 partial、合并、同步和启动。短行很多时比较[Merge-row](ar-merge-row.md)，不要为凑核数强行跨行统计。

## 地址、统计与输出

- 单行槽位每次新载一行，归约从该槽位起点计算；不能把全局行号乘行距再索引这个单行槽位。
- 多行驻留时行距用对齐容量，搬运/Reduce count 用有效 R；padding 不污染统计。
- 所有 chunk 完成后完整统计量才可用于 Norm/Softmax 输出，局部概率不能直接拼成全行概率。
- 最终标量/统计必须写到真实 GM 输出；仅在 UB 产生 Reduce 结果不等于交付输出。没有标量控制需求时不必为写回而 GetValue。
- 统计跨输出阶段驻留，不能因统计完成就在 UB 账本扣除；分段输出覆盖每个位置且不重复写。

归一化或融合场景继续读[Norm 的保留/重读/重算](norm-fusion.md)，不要默认为分段统计必须把原输入先写一遍 GM。浮点累积顺序、极值和多输出遵守原合同，精度失败不自动归因为“FP16不够”。
