# Reduce 类算子 - AR 全载分支

> **适用场景**: A0=1（尾轴）, 整行工作集可驻留 UB（`R ≤ R_max`，R_max 由 3.1 的账本公式给出）
>
> 本文平台常数（对齐字节数等）与所有数字均为**合成示例**，非平台查询或实测结果；
> 实际任务用平台查询回填常数后按公式重算。全载判定是可行性（账本放得下），
> 不代表该候选最优（最优性按 workload 比较）。

---

## 目录

- [一、分支特征](#一分支特征)
- [二、Buffer 规划](#二buffer-规划)
- [三、Tiling 参数计算](#三tiling-参数计算)
- [四、Kernel 实现要点](#四kernel-实现要点)
- [五、常见问题](#五常见问题)
- [六、性能/精度优化建议](#六性能精度优化建议)

---

## 一、分支特征

| 特征 | 说明 |
|------|------|
| **模板类型** | AR 模板（A 轴 + R 轴） |
| **Shape 抽象** | (A1, R) |
| **载入模式** | 全载（整行完整放入 UB） |
| **适用条件** | A0=1, `copies×align_up(R×inBytes, alignBytes) + outBytes + accumBytes + tmpBufSize ≤ ubSize - reserveBytes`（见 3.1 全载阈值 R_max） |
| **数据连续性** | 每行 R 个元素连续 |
| **Reduce 结果** | 标量（1 个值/行） |

> 多行批量搬运/多行合并是另一条 AR 子路线（MergeN），不是本分支的参数变体，
> 见 [ar-merge-row.md](ar-merge-row.md)。

---

## 二、Buffer 规划

### 2.1 Kernel 侧（fp16 输入示例，copies=2）

每行在 UB 内按**对齐后的行长度**存放：`rLengthAlign = align_up(R, alignElems)`，
其中 `alignElems = alignBytes / elemBytes`（示例 `alignBytes = 32`；要求 `elemBytes` 整除 `alignBytes`）。
旧示例 `R * sizeof(float)` 是 fp32 且 `alignElems = 8` 时 `rLengthAlign * 4 == align_up(R*4, 32)` 的特例；
R 不是对齐元素数的整数倍时，按 `R * sizeof(float)` 分配会装不下 padding，必须用 `rLengthAlign`。

```cpp
constexpr int alignBytes = 32;  // 示例值，平台查询
int32_t alignElems = alignBytes / sizeof(T);                  // fp32→8, fp16→16
uint32_t rLengthAlign = (R + alignElems - 1) / alignElems * alignElems;

pipe->InitBuffer(inQueueX, 2, rLengthAlign * sizeof(T));      // 输入，copies=2（double buffer）
pipe->InitBuffer(outQueueY, 2, alignBytes);                   // Reduce 标量结果，按一个对齐块
pipe->InitBuffer(tmpBuf, tmpBufSize);                         // Reduce API scratch

// 这个例子中输出队列深度为 2，outBytes = 2 * alignBytes。
// 总 UB = copies * rLengthAlign * sizeof(T) + outBytes + tmpBufSize
//       + reserveBytes + accumBytes（若另有独立的统计驻留，须计入）
```

### 2.2 tmpBufSize 计算（Host侧）

```cpp
uint32_t ComputeReduceBufSize(uint32_t rLengthAlign, uint32_t typeSize) {
    uint32_t perRepeat = 256 / typeSize;  // 64 for FP32
    uint32_t perBlock = 32 / typeSize;     // 8 for FP32
    uint32_t repeats = (rLengthAlign + perRepeat - 1) / perRepeat;
    uint32_t tmpBufSize = ((repeats + perBlock - 1) / perBlock) * perBlock * typeSize;
    return std::max(tmpBufSize, 4096u);  // 最小 4KB（示例值）
}
```

> scratch 上限以目标环境 SDK 查询为准（`Get*MaxMinTmpSize` 类接口或 [tiling-fields.md](tiling-fields.md) 公式），
> 不要硬编码跨平台常数。

---

## 三、Tiling 参数计算

### 3.1 全载阈值 R_max

整行可行性由物理字节账本决定。**定义式**（唯一权威，任何 dtype/平台可测）：

```text
R_max = max{ R ≥ 1 : copies * align_up(R * inBytes, alignBytes)
                     + outBytes + accumBytes + tmpBufSize
             ≤ ubSize - reserveBytes }

align_up(x, a) = ceil_div(x, a) * a   （ceil_div(x,a) = (x + a - 1) / a，int64 运算）
```

各项含义：

| 项 | 含义 |
|----|------|
| `copies` | 该统计阶段同一输入的物理份数 = queue 槽位深度 × 每槽份数（double buffer 时 ≥ 2）。深度是账本项，不代表搬运与计算一定重叠（见 [../common/resource-lifetime.md](../common/resource-lifetime.md)） |
| `inBytes` | 输入元素字节数 |
| `outBytes` | 归约标量输出的全部物理 buffer 字节数，包含输出队列所有槽位和独立输出 buffer；例如上方输出队列深度 2、每槽 32B 时为 64B。与其他账本项不重复计算 |
| `accumBytes` | FP32 累加/统计驻留中**与 R 无关**的部分（标量累加器、统计缓冲等）。若分支需要整行 FP32 中间（升精度），该项变为 `accumCopies * align_up(R * sizeof(float), alignBytes)`，随 R 变化，闭式不再成立，需按定义式从无对齐上界向下收缩（方法与 [../elewise/tiling.md](../elewise/tiling.md) 第六节相同） |
| `tmpBufSize` | Reduce API scratch（[tiling-fields.md](tiling-fields.md)） |
| `reserveBytes` | 参数驻留（gamma 等）、对齐与其他常驻，来自资源账本，**不能凭空填 0** |

**闭式**（`accumBytes` 与 R 无关，且 `elemBytes` 整除 `alignBytes` 时精确成立）：

```text
R_max = floor_div(ubSize - reserveBytes - outBytes - accumBytes - tmpBufSize,
                  copies * alignBytes) * (alignBytes / elemBytes)
```

**Worked example（全部为合成示例值；此例输入队列深度 2、输出队列深度 1，与上方代码片段不同）**：
`ubSize = 100000`，`reserveBytes = 1000`，`copies = 2`，`inBytes = 2`（fp16），
`outBytes = 32`（输出队列 1 槽），`accumBytes = 256`（独立统计驻留），`tmpBufSize = 4000`，`alignBytes = 32`：

- 分子 `X = 100000 - 1000 - 32 - 256 - 4000 = 94712`
- `R_max = floor_div(94712, 2 * 32) * (32 / 2) = floor_div(94712, 64) * 16 = 1479 * 16 = 23664`
- 核对 R = 23664：每份 `23664 * 2 = 47328 = 1479 * 32`（已对齐）；两份 `94656`；
  合计 `94656 + 32 + 256 + 4000 = 98944 ≤ 100000 - 1000 = 99000` ✓（余 56 字节：94712 = 1479×64 + 56）
- 核对 R = 23665：`47330 → ceil_div(47330, 32) = 1480 → 47360`；两份 `94720 > 94712` ✗

R_max 是**可行性边界**，不是"取到 R_max 就最快"的结论；是否用更小的 tile 换其他收益，按 workload 评估。

### 3.2 多核切分参数（Host侧）

```cpp
// 按 A1（行）切分
uint32_t rowsPerCore = (A1 + blockDim - 1) / blockDim;
uint32_t usedCoreNum = (A1 + rowsPerCore - 1) / rowsPerCore;
uint32_t tailCoreRows = A1 % rowsPerCore;
if (tailCoreRows == 0 && A1 > 0) tailCoreRows = rowsPerCore;
```

> 启动块数 ≥ 有非空工作的活跃块数；尾波与空块的账本口径见
> [../common/resource-lifetime.md](../common/resource-lifetime.md)。

### 3.3 对齐处理（Kernel侧）

```cpp
// 通用形式：对齐后的列数（fp32 时等价于 align_up(R*4, 32)/4）
uint32_t alignElems = 32 / sizeof(T);
uint32_t rLengthAlign = (R + alignElems - 1) / alignElems * alignElems;

// 使用 DataCopyPad 处理非对齐（只拷贝一行。若UB较富余，可以多行批量拷贝——
// 多行批量属于 MergeN 子路线，见 ar-merge-row.md）
DataCopyExtParams copyParams{1, static_cast<uint32_t>(R * sizeof(float)), 0, 0, 0};
DataCopyPadExtParams<float> padParams{false, 0, 0, 0};
DataCopyPad(xLocal, xGm[offset], copyParams, padParams);
```

记忆口径：**搬运/Reduce 的 count 用 `R`（有效数据），单行槽位容量用 `rLengthAlign`**；仅当多行同时驻留同一槽位时，UB 内相邻行距才用 `rLengthAlign`。

---

## 四、Kernel 实现要点

### 4.1 数据流（含统计量写回）

```
GM (A1, R) --DataCopyPad(count=R)--> UB (rLengthAlign)
    ↓ EnQue / DeQue
[ReduceMax/ReduceSum, count=R] → resultLocal（标量，驻留 UB）
    ↓ EnQue / DeQue
DataCopyPad(yGm[row], resultLocal) → GM (A1)
```

统计量必须真正写回 GM：Reduce 结果先驻留 UB，经输出队列（或直接 DataCopyPad）搬出，
否则归约结果不会出现在输出张量中。

### 4.2 核心 API 调用（Kernel侧）

> 下列片段只示意逐行数据流和地址；具体接口、dtype 与对齐约束以目标 SDK 为准，片段本身不代表可直接编译。

```cpp
for (uint32_t row = 0; row < rowsThisCore; row++) {
    LocalTensor<T> xLocal = inQueueX.AllocTensor<T>();
    DataCopyExtParams inParams{1, static_cast<uint32_t>(rLength * sizeof(T)), 0, 0, 0};
    DataCopyPad(xLocal, xGm[(int64_t)(rowStart + row) * R], inParams, padParams);
    inQueueX.EnQue(xLocal);
    LocalTensor<T> xDe = inQueueX.DeQue<T>();

    // 每次槽位只载入一行，归约从该槽位的第 0 个元素开始
    // count 用有效数据个数 rLength（不含 padding）
    ReduceSum<T>(resultLocal, xDe[0], tmpLocal, static_cast<int32_t>(rLength), false);
    inQueueX.FreeTensor(xDe);

    // 按目标 SDK 支持的方式将本行 resultLocal 写回 yGm[rowStart + row]，
    // 输出缓冲的实际物理分配须纳入 outBytes。
}
```

**关键要点**:
- 单行槽位：每轮重新载入一行，归约从 `xDe[0]` 开始；不得将全局或核内行号乘行距后用于该槽位
- API `count` 参数：用 `rLength`（只处理有效数据，不包括 padding）
- Buffer 大小：用 `rLengthAlign`（需要容纳对齐后的数据）
- `GetValue(0)` 会触发 UB→标量读回并同步等待；仅在后续标量逻辑确实需要该值时使用
  （跨 chunk 合并、分支判断）。纯输出场景不必读回。
- **队列槽位生命周期**：物理队列在 `InitBuffer(queue, depth, size)` 时按深度一次性分配，
  pipe 生命周期内不会因"最后一次使用"而释放；账本不能因逻辑上不再读取而扣除该槽位。
  深度 2 只是流水重叠的必要条件——还需要循环结构与事件配对支撑，不代表搬运与计算一定重叠。
  详见 [../common/resource-lifetime.md](../common/resource-lifetime.md)。

### 4.3 流水线设计

**Double Buffer 模式** (`InitBuffer(que, 2, size)`):
```
Tile N:   CopyIn(row0) → Compute(row0) → CopyOut(row0)
Tile N+1:              CopyIn(row1) → Compute(row1) → CopyOut(row1)
```

单缓冲/双缓冲是选择题：每核 tile 数 ≥ 2 且核数不减少时才值得评估双缓冲（结构性判据，
非万能阈值）；深度翻倍会挤占 R_max，需要按 3.1 重算。

---

## 五、常见问题

| 问题 | 原因 | 解决方案 |
|-----|------|---------|
| 输出全 0 | Buffer 未正确初始化 | 检查 AllocTensor/FreeTensor 配对 |
| 归约结果没有出现在 GM | 统计量停留在 UB 未搬出 | 按 4.1 完成 EnQue/DataCopyPad 写回 |
| FP16 精度差 | 中间计算精度不足 | 使用 FP32 中间计算（accumBytes 计入账本后重算 R_max） |
| 非对齐场景精度错误 | count 用 rLengthAlign 而非 rLength | count 参数用 `rLength`（有效数据个数） |
| 多行数据错误 | rowOffset 计算错误 | rowOffset 用 `rLengthAlign`（UB 按对齐存储） |
| UB 越界 | buffer 按 `R*sizeof(T)` 而非 `rLengthAlign*sizeof(T)` 分配 | 对齐后的行长作为分配口径 |

---

## 六、性能/精度优化建议

1. **Double Buffer**: 使用 `InitBuffer(que, 2, size)` 开启, CopyIn/Compute/CopyOut 并行；
   是否启用按 4.3 的结构性判据评估，深度计入 copies 后重算 3.1
2. **FP16 混合精度**: Sum/Mean/Prod等计算归约场景下：BF16/FP16 输入，FP32 计算，BF16/FP16 输出
3. **dtype 注意**: 同一 kernel 模板在不同 dtype 下字节账本不同（`inBytes`、`accumBytes`、对齐元素数都变），
   可能改变整行可行性与策略选择（fp16 下全载可行、升精度后可能转为核内 SplitD）；
   dtype 分支本身不等于调度自适应
4. **多行合并**: 行较短、行数多时评估 MergeN 子路线，见 [ar-merge-row.md](ar-merge-row.md)
