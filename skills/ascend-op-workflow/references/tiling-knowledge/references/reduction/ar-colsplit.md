# Reduce 类算子 - AR Col-Split 分支（核内 SplitD）

> **适用场景**: A0=1（尾轴），沿 R 分 chunk 处理（`R > chunkCols`，chunkCols 由 2.2 的本分支账本给出）；整行全载可行性另按全载分支实际账本判断。
>
> 本文平台常数与所有数字均为**合成示例**，非平台查询或实测结果。
> 分载是整行可行性（UB 账本）不满足时的候选路线；核内 SplitD **不增加核间行并行度**，
> 是否比分载外的其他组织更快，按 workload 评估。

---

## 目录

- [一、分支特征](#一分支特征)
- [二、Buffer 规划](#二buffer-规划)
- [三、Tiling 参数计算](#三tiling-参数计算)
- [四、Kernel 实现要点](#四kernel-实现要点)
- [五、统计 → 保留/重读/重算 → 输出（SplitD 契约）](#五统计--保留重读重算--输出splitd-契约)
- [六、常见问题](#六常见问题)
- [七、性能优化建议](#七性能优化建议)

---

## 一、分支特征

| 特征 | 说明 |
|------|------|
| **模板类型** | AR 模板（A 轴 + R 轴） |
| **Shape 抽象** | (A1, R) |
| **载入模式** | 分载（整行放不下，分 chunk 处理） |
| **适用条件** | A0=1，`R > chunkCols`；整行全载是否可行按 [ar-fullload.md](ar-fullload.md) 3.1 的实际账本判断 |
| **切分方向** | 列方向（沿 R 分 chunk），同一核内循环 |
| **数据连续性** | 每行 R 个元素连续 |
| **Reduce 结果** | 标量（1 个值/行） |
| **并行度** | 核间仍按行分；核内分 chunk 不产生新的核间任务 |

---

## 二、Buffer 规划

### 2.1 Kernel 侧（fp32 示例，分 chunk 循环）

```cpp
// 单槽示意：此 SplitD 分支的 chunkCols 为对齐后的元素数
pipe->InitBuffer(inQueueX, 1, chunkCols * sizeof(float));
pipe->InitBuffer(outQueueY, 1, alignBytes);        // Reduce结果（1个标量，按对齐块，示例 32B）
pipe->InitBuffer(chunkResultBuf, 1, alignBytes);   // chunk中间结果
pipe->InitBuffer(tmpBuf, 1, tmpBufSize);

// 总 UB = copies * align_up(chunkCols * inBytes, alignBytes)
//       + scalarBuffersBytes + tmpBufSize + statsBytes + reserveBytes
// 此例两个独立单槽标量缓冲合计 scalarBuffersBytes = 2 * alignBytes。
// statsBytes、reserveBytes 不重复包含这些缓冲或其他已列项。
```

### 2.2 chunkCols 计算（Host侧，完整公式）

```text
B            = ubSize - reserveBytes - statsBytes - tmpBufSize - scalarBuffersBytes
chunkCols_raw = floor_div(B, copies * inBytes)                      # 字节口径上界
chunkCols     = min( floor_div(chunkCols_raw, alignElems) * alignElems, R )   # 对齐元素数向下取整后 clamp 到 R
```

闭式（`inBytes` 整除 `alignBytes` 时与两步式结果相同）：

```text
chunkCols = min( floor_div(B, copies * alignBytes) * (alignBytes / inBytes), R )
```

符号定义：

| 符号 | 含义 |
|------|------|
| `ubSize` | UB 总容量（平台查询值） |
| `reserveBytes` | 参数/对齐/其他常驻 buffer 预留的字节数，来自资源账本，不能凭空填 0；不重复包含其他已列物理分配 |
| `statsBytes` | 与下列两个标量缓冲互不别名的本行统计量驻留字节数（分段累计的 sum/sumsq/max 等标量或其向量形式，按实际分配和对齐计）；若使用同一物理槽，只计一次 |
| `tmpBufSize` | Reduce API scratch（见 [tiling-fields.md](tiling-fields.md)） |
| `copies` | 该统计阶段同一输入的物理份数（queue 槽位深度 × 每槽份数） |
| `inBytes` | 输入元素字节数 |
| `alignElems` | `alignBytes / inBytes`（要求 inBytes 整除 alignBytes；不整除时逐 buffer `align_up` 求解，方法同 [../elewise/tiling.md](../elewise/tiling.md) 第六节） |
| `scalarBuffersBytes` | 输出队列和 chunk 中间结果的全部独立物理槽位字节数；2.1 各为一个 `alignBytes` 槽时等于 `2 * alignBytes`，深度或大小变化须重新计算 |

约束：`chunkCols ≥ 1`；`B ≤ 0` 或 `chunkCols ≤ 0` ⇒ 本分支参数不可行，回资源账本检查，
不能继续用 0 作除数计算 numChunks。
闭式假设 `statsBytes`、`tmpBufSize` 和其他非输入项与 chunkCols 无关或取覆盖该候选的保守上界；
若它们随 chunkCols 变化，应按实际物理字节不等式重求并验证。若 clamp 到未对齐的 R，
输入槽仍按 `align_up(chunkCols * inBytes, alignBytes)` 分配。

**Worked example（全部为合成示例值）**：
`ubSize = 100000`，`reserveBytes = 1000`，`statsBytes = 128`，`tmpBufSize = 4000`，
`copies = 2`（输入队列 2 槽），两个独立标量缓冲各 1 槽，
`inBytes = 4`（fp32），`alignBytes = 32`（⇒ `alignElems = 8`）：

- `scalarBuffersBytes = 2 * 32 = 64`；`B = 100000 - 1000 - 128 - 4000 - 64 = 94808`
- `chunkCols_raw = floor_div(94808, 2 * 4) = 11851`（8 × 11851 = 94808）
- 对齐向下取整：`floor_div(11851, 8) * 8 = 1481 * 8 = 11848`（对齐咬掉 3 个元素）
- 闭式核对：`floor_div(94808, 2 * 32) * (32 / 4) = floor_div(94808, 64) * 8 = 1481 * 8 = 11848` ✓
- 物理核对：每份 `11848 * 4 = 47392 = 1481 * 32`；两份 `94784`；
  合计 `94784 + 64 + 1000 + 128 + 4000 = 99976 ≤ 100000` ✓。
  下一对齐档 `11856` 则为 `94848 + 64 + 1000 + 128 + 4000 = 100040 > 100000`。
- clamp 与分块（合成 `R = 50000`）：`chunkCols = min(11848, 50000) = 11848`；
  `numChunks = ceil_div(50000, 11848) = 5`；`lastChunk = 50000 - 4 * 11848 = 2608`
- 尾块核对：`2608 * 4 = 10432 = 326 * 32`（对齐，装得进单份 buffer）✓

---

## 三、Tiling 参数计算

### 3.1 分载判定

`chunkCols` 是本分支账本下单次搬入的列数上限，经 R 截断。
`R > chunkCols` 表示在本分支账本下需分段；是否存在不同账本的可行全载方案，
应单独核对 [ar-fullload.md](ar-fullload.md) 3.1，不能仅凭本分支阈值推断。

### 3.2 多核切分参数（Host侧）

```cpp
// 按 A1（行）切分；核内分 chunk 不改变核间任务结构
uint32_t rowsPerCore = (A1 + blockDim - 1) / blockDim;
uint32_t usedCoreNum = (A1 + rowsPerCore - 1) / rowsPerCore;
uint32_t tailCoreRows = A1 % rowsPerCore;
if (tailCoreRows == 0 && A1 > 0) tailCoreRows = rowsPerCore;
```

---

## 四、Kernel 实现要点

### 4.1 数据流

```
GM (A1, R) → 分 chunk 处理
    ↓
Chunk 0: GM[0:chunkCols] → UB
    ↓
[ReduceMax] → chunkResult_0
    ↓
[更新 globalResult] → globalResult = merge(globalResult, chunkResult_0)
    ↓
Chunk 1, 2, ... (重复)
    ↓
UB → GM (A1)
```

### 4.2 核心 API 调用

#### ReduceMax 分载实现（Kernel侧）

```cpp
// 初始化全局最大值为 -∞
float globalMax = -INFINITY;

for (uint32_t chunkIdx = 0; chunkIdx < numChunks; chunkIdx++) {
    uint32_t chunkStart = chunkIdx * chunkCols;
    uint32_t chunkSize = (chunkIdx == numChunks - 1) ? lastChunkSize : chunkCols;

    // Load chunk. use `DataCopyPad` in case last chunk is not 32 bytes aligned.
    DataCopyExtParams copyParams{1, static_cast<uint32_t>(chunkSize * sizeof(float)), 0, 0, 0};
    DataCopyPadExtParams<float> padParams{false, 0, 0, 0};
    DataCopyPad(xLocal, xGm[chunkStart], copyParams, padParams);

    // ReduceMax for this chunk
    ReduceMax<float>(chunkResultLocal, xLocal, tmpLocal, chunkSize, false);
    float chunkMax = chunkResultLocal.GetValue(0);

    // Update `globalMax`. DO NOT use `std::` function.
    if (chunkMax > globalMax) {
        globalMax = chunkMax;
    }
}

// use `globalMax` to complete the rest calculation...
```

### 4.3 关键注意点

1. **跨 chunk 合并**:
   - ReduceMax: 使用 `if` 或者 `三目运算` 取最大值
   - ReduceSum: 使用 `+=` API 累加
2. **边界处理**: 最后一个 chunk 的大小可能小于 chunkCols。搬入/搬出时需要使用`DataCopyPad`
3. **初始化**:
   - ReduceMax: 初始化为 `-INFINITY` 或数据类型的最小值
   - ReduceSum: 初始化为 `0`
4. **有效长度守卫**: 每次搬入/归约都按当次 `chunkSize`（尾块为 `lastChunkSize`），
   padding 值不得进入统计量（padValue 对 sum 安全、对 max 不安全，需按语义守卫或选值）

### 4.4 单缓冲 / 双缓冲

分 chunk 循环存在流水空间（chunk 数多、搬运与计算可交叠）时才评估 depth 2；
深度翻倍会按 2.2 公式挤占 `chunkCols`（copies 翻倍 ⇒ chunkCols 近似减半），需要重算可行性。
单缓冲/双缓冲是选择题，无万能阈值。

---

## 五、统计 → 保留/重读/重算 → 输出（SplitD 契约）

分段统计得到每行统计量后，输出段有三种**合法组织**。共同契约：

- 统计量必须基于**完整 R**（所有 chunk 都参与统计后，统计量才可用）；
- 输出段不得重复或遗漏任何列段（按 chunkIdx 索引驱动，段边界由 tiling 参数唯一决定）；
- `statsBytes` 在整个统计 + 输出期间驻留，生命周期跨阶段，
  不得因"统计已完成"而从账本扣除（见 [../common/resource-lifetime.md](../common/resource-lifetime.md)）。

| 组织 | 做法 | GM 读次数/行 | UB 峰值 | 同步/复杂度 |
|------|------|--------------|---------|-------------|
| **(a) 保留** | 整行仍驻留 UB（仅当统计后工作集仍放得下：`copies×整行对齐字节 + stats + … ≤ ubSize`） | 1 | 最高 | 最低（无二次搬运） |
| **(b) 重读** | 第一遍把需要的中间（如残差和 x）写回 GM，第二遍按 D 段**重读 GM 中已写回的数据**，用保留的统计量算输出 | 第一遍 1 + 第二遍 1（对被重读的中间） | 最低（只有 D 段） | 需两遍循环与写回；GM 流量计入成本 |
| **(c) 重算** | 从 UB 内保留的输入段重算输出段（适用于段内可重算且不重读 GM） | 1 | 中（需保留可重算的输入段） | 一遍半循环；重算指令开销计入成本 |

- 选择依据是**账本可行性 + workload 成本**，没有默认答案；(a) 放不下才在 (b)/(c) 间比较。
- 重读组织里，"第一遍写回、第二遍重读"的写与读都是真实 GM 流量，
  与 (c) 的"零额外 GM 流量、多花指令"是不同的成本结构。
- Norm/融合算子的完整三阶段流程（统计 → 中间 → 输出、第二个输出与统计量写回、
  融合增量入账）见 [norm-fusion.md](norm-fusion.md)。

---

## 六、常见问题

| 问题 | 原因 | 解决方案 |
|-----|------|---------|
| 精度下降 | chunk 合并逻辑错误 | 确保正确合并（Max取最大值，Sum累加） |
| 输出错误 | 最后一个 chunk 大小处理错误 | 使用 lastChunkSize 而非 chunkCols |
| 输出段重复/遗漏 | 段索引或段边界计算错误 | 段边界只由 `chunkIdx * chunkCols` 与 `lastChunkSize` 决定，逐段唯一 |
| 性能差 | 多次遍历数据 | 优化 chunk 策略，减少遍历次数；比较第五节的三种组织 |
| Buffer 不足 | chunkCols 计算错误或漏计 statsBytes | 按 2.2 完整公式计算，账本项逐项列全 |

---

## 七、性能优化建议

1. **chunk 大小优化**: 按 2.2 公式取账本允许的最大 chunk（减少 chunk 数量）；
   但 chunk 大小是可行性上界，是否取满由 workload 决定
2. **避免不必要的数据拷贝**: 直接在chunk结果上合并，减少中间存储
3. **单双缓冲**: 见 4.4，评估时重算 chunkCols
4. **融合与多行**: 融合 trait 改变账本后重算，见 [norm-fusion.md](norm-fusion.md)；
   行较短且行多时先确认整行可行性（可能回到 FullLoad/MergeN 路线），见
   [ar-fullload.md](ar-fullload.md) 与 [ar-merge-row.md](ar-merge-row.md)
