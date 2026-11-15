# Reduce 类算子 - AR 多行合并分支（MergeN / Merge-row）

> **适用场景**: A0=1（尾轴），整行工作集可驻留 UB 且行较短、行数多；
> 一个 tile 装入 `B_M` 行，**行间统计与计算完全独立（不跨行归约）**。
>
> 3.0.0-experimental 新增设计卡。MergeN **不是必须分支**：是否采用由可行性
> （UB 账本）与 workload 评估共同决定。本文所有数字均为合成示例，
> 非平台查询或实测结果；平台常数（对齐字节数等）需平台查询回填。

---

## 目录

- [一、分支特征](#一分支特征)
- [二、Buffer 规划（UB 账本）](#二buffer-规划ub-账本)
- [三、Tiling 参数计算（两种任务数公式）](#三tiling-参数计算两种任务数公式)
- [四、Kernel 实现要点](#四kernel-实现要点)
- [五、常见问题](#五常见问题)
- [六、性能建议](#六性能建议)

---

## 一、分支特征

| 特征 | 说明 |
|------|------|
| **模板类型** | AR 模板的 MergeN 子路线（A 轴 + R 轴，tile 内多行） |
| **Shape 抽象** | (M, R)，M = A1 为行数 |
| **载入模式** | 整行驻留 + 多行合并（一个 tile 装 B_M 行） |
| **适用候选** | 整行工作集可驻留（同 [ar-fullload.md](ar-fullload.md) 判定）且 行较短、行数多；合并后任务数仍能提供核间并行度 |
| **语义约束** | 行间统计与计算完全独立，不跨行归约（跨行有依赖的归约不是 MergeN，见 [patterns.md](patterns.md) S5/S6） |
| **Reduce 结果** | 每行一个标量（每 tile B_M 个） |

**与相邻分支的边界**：

- 整行工作集**放不下** UB → 不是 MergeN，走核内 SplitD，见 [ar-colsplit.md](ar-colsplit.md)。
- 单行 FullLoad 已能提供足够并行度、或合并收益不明确 → 直接用按行 FullLoad，
  见 [ar-fullload.md](ar-fullload.md)（MergeN 不是必须）。
- 行数少且单行极长、需要跨核拆行 → 可选条件策略 Group Reduce，见 [patterns.md](patterns.md) S5。

---

## 二、Buffer 规划（UB 账本）

```text
copies * B_M * rowAlignedBytes
  + statsBytes(B_M) + outCopies * align_up(B_M * outElemBytes, alignBytes)
  + tmpBytes(B_M) + reserveBytes ≤ ubSize

rowAlignedBytes = align_up(R, alignElems) * inBytes        # 用对齐后的行长度
alignElems      = alignBytes / inBytes                     # 要求 inBytes 整除 alignBytes
```

此式示意单个输入队列和每行一个输出元素的输出队列；其他物理 buffer 按实际分配逐项加入。
各项按实际生命周期计一次：统计、输出、scratch、reserve 若有物理别名，不得重复计算；
若彼此独立，不得遗漏。槽位大小的对齐与设备约束以目标平台为准。

| 项 | 含义 |
|----|------|
| `copies` | 输入 queue 槽位深度 × 每槽份数（double buffer ≥ 2；深度是账本项，不证明重叠） |
| `statsBytes(B_M)` | 与输入、输出和 scratch 独立的统计量 buffer 实际总字节数，含对齐；可随合并行数变化 |
| `outCopies` / `outElemBytes` | 输出队列物理槽位数 / 单行输出元素字节数；每个槽按实际大小对齐 |
| `tmpBytes(B_M)` | 独立 scratch 的实际总字节数；可随合并行数变化，以目标 API 的要求为准 |
| `reserveBytes` | 参数驻留（gamma/scale 等 R 长参数，一次载入、多 tile 复用）、其他常驻；与已列项不重复，**参数驻留与行合并争抢同一 UB 预算** |

物理生命周期口径（队列槽位不因"最后一次使用"释放、显式释放时机）见
[../common/resource-lifetime.md](../common/resource-lifetime.md)。

```cpp
// Kernel 侧（示例）：一个 tile 的行距按对齐后行长存放
int32_t alignElems = alignBytes / sizeof(T);
uint32_t rowAlignElems = (R + alignElems - 1) / alignElems * alignElems;
pipe->InitBuffer(inQueueX, 2, B_M * rowAlignElems * sizeof(T));  // copies=2
pipe->InitBuffer(outQueueY, 2, align_up(B_M * sizeof(T), alignBytes)); // B_M 个标量结果
pipe->InitBuffer(tmpBuf, tmpBufSize);
// 若另有统计驻留，按实际物理分配计入 statsBytes(B_M)。
// 参数（gamma 等）驻留单独一块，计入 reserveBytes；不重复计入其他项。
```

---

## 三、Tiling 参数计算（两种任务数公式）

`B_M` 的 **UB 上限**（两种任务结构下相同）：

```text
B_M_max = max { b ≥ 1 : copies * b * rowAlignedBytes
                          + statsBytes(b) + outCopies * align_up(b * outElemBytes, alignBytes)
                          + tmpBytes(b) + reserveBytes ≤ ubSize }
```

不存在满足条件的正整数时本分支不可行。若实际 buffer 大小随 b 变化，按实际分配查询并求解；
只有所有线性和常驻项已完整纳入、且适用相应假设或保守上界时，才能使用简化闭式。

两种任务数公式对应**不同的并行结构**，二选一（细节差异见下）：

### (a) 行组全局分发

先把 M 行切成 `ceil(M / B_M)` 个行组，行组作为独立任务分给核：

```text
Q = ceil_div(M, B_M)          # 任务数，可远大于核数，按波次执行
B_M ≤ B_M_max                 # UB 账本上限
```

行组可被调度器迁移到任意核，负载更均衡；代价是任务调度开销随 Q 增大。
`Q` 需足够支撑核间并行（并行度检查，不是"必须用满核"，也不设固定阈值）。

### (b) 核内预分配行再合并

先按行分核，每核在自己分到的行内再合并：

```text
# M > 0、P > 0；P 为启动核数，不超过平台可用核数
rowsPerCore = ceil_div(M, P)
usedCoreNum = ceil_div(M, rowsPerCore)     # 非空核数，≤ P
rowStart = coreIdx * rowsPerCore
rowsThisCore = max(0, min(rowsPerCore, M - rowStart))
每个非空核的 tile 数 = ceil_div(rowsThisCore, B_M)
B_M ≤ min(B_M_max, rowsPerCore)           # 合并不跨核
```

核间无行组重分配，每核的固定成本（参数载入、初始化）一次性摊销；
代价是核间负载可能不均（尾核行数少）。`rowsThisCore = 0` 的核不访问 GM；
即使 `M ≥ P` 也可能因向上取整出现空核。M=0 等边界按算子规格由 host 另行处理。

### 尾行组 / 尾行处理（按任务结构分别计算）

对 (a)，`M > 0` 时全局末组的有效行数是

```text
valid = M - (ceil_div(M, B_M) - 1) * B_M
```

对 (b)，每个非空核必须按自己的 `rowsThisCore` 算末 tile：

```text
valid = rowsThisCore - (ceil_div(rowsThisCore, B_M) - 1) * B_M
```

两式所得 `1 ≤ valid ≤ B_M`。空行槽**不读写 GM**（越界守卫），统计只对有效行
（循环按 `valid` 迭代而非 `B_M`；结果写出同样只写 `valid` 个）。
每个 tile 也可用 `valid = min(B_M, rowsThisCore - tileIdx * B_M)`，仅对非空且有效的 tileIdx 计算。

### Worked example（全部为合成示例值）

`M = 8192`，`R = 128`，`inBytes = outElemBytes = 2`（fp16），
`copies = outCopies = 2`，`alignBytes = 32`，`statsBytes(b) = 32 * b`，
`tmpBytes(b) = 512`，`reserveBytes = 1024`（含 gamma 驻留），`ubSize = 100000`。
这里统计、输出、scratch 和 reserve 互为独立分配，数值均为合成假设：

- `rowAlignedBytes = align_up(128 * 2, 32) = 256`（128×2 = 256 = 8×32，已对齐）
- `b = 179`：输入 `2*179*256 = 91648`、统计 `5728`、输出 `2*align_up(358,32) = 768`、
  scratch `512`、reserve `1024`；总计 `99680 ≤ 100000`
- `b = 180`：输入 `92160`、统计 `5760`、输出 `768`、scratch `512`、reserve `1024`；
  总计 `100224 > 100000`。这些项随 b 非减，故 `B_M_max = 179`。
- **(a)** 取 `B_M = 96`（示例：由并行度与 tile 粒度约束选，不必取 UB 上限）：
  输入 `49152` + 统计 `3072` + 输出 `384` + scratch `512` + reserve `1024`
  = `54144 ≤ 100000` ✓；`Q = ceil_div(8192, 96) = 86` 个行组；
  尾组 `valid = 8192 - 85 * 96 = 32` 行（96 个行槽中只有 32 个有效，其余守卫跳过）
- **(b)** 取 `P = 40`（示例）：`rowsPerCore = ceil_div(8192, 40) = 205`；
  前 39 核各 205 行、各 3 个 tile，尾 tile 各 13 行；
  最后一核 `rowsThisCore = 8192 - 39 * 205 = 197`，3 个 tile，尾 tile `197 - 2 * 96 = 5` 行。

---

## 四、Kernel 实现要点

```
GM (M, R) --DataCopyPad(B_M 行)--> UB (B_M × rowAlignElems)
    ↓ EnQue / DeQue
for (r = 0; r < valid; ++r):                      # 只对有效行
    ReduceSum<T>(resultLocal[r * 槽距], xDe[r * rowAlignElems], tmpLocal, R, false)
    ↓
outQueue EnQue/DeQue → DataCopyPad → GM (M)       # B_M（或尾组 valid）个标量
```

- **rowOffset 用对齐后行距**（`rowAlignElems`），Reduce `count` 用有效长度 `R`，
  与 [ar-fullload.md](ar-fullload.md) 的口径一致。
- 参数驻留（gamma 等）一次载入、多个 tile 复用；驻留期覆盖全部 tile，
  账本上计入 `reserveBytes`，不得按 tile 重复计或漏计。
- 多行结果可攒在结果 tensor 中成块搬出，减少每行一次的标量搬运；
  是否更优由 workload 评估，不作为默认规则。
- 队列深度、事件配对与槽位生命周期见 [../common/resource-lifetime.md](../common/resource-lifetime.md)。

---

## 五、常见问题

| 问题 | 原因 | 解决方案 |
|-----|------|---------|
| GM 越界读写 | 尾组空行槽仍按 B_M 搬运 | 只搬/算/写 `valid` 行，空槽守卫 |
| 统计被污染 | 跨行归约（把 B_M 行当一个向量归约） | 行间必须独立：逐行归约，stride 用对齐行距 |
| 核间并行不足 | 全局行组的 `Q = ceil_div(M, B_M)` 或预分配的非空核数不足以提供所需工作量 | 结合可执行核数、波次和固定开销评估更小的 `B_M` 或按行 FullLoad；不设固定阈值 |
| UB 越界 | `B_M` 直接取 UB 上限后 dtype/融合变化未重算 | 逐项按 dtype、槽位、scratch 和融合变化重算物理账本，再求 `B_M_max` |
| 参数漏计 | gamma/scale 驻留未入 `reserveBytes` | 参数驻留与行合并争抢同一预算，入账后重解 |

---

## 六、性能建议

1. **并行度与合并**：结合全局行组数 `Q` 或预分配非空核数 `usedCoreNum`、可执行核数和波次比较；
   `rowsPerCore` 小只表示每核工作量少及固定开销摊销空间小，不能单独推断并行不足。
   `B_M` 不是越大越好，也不设固定阈值。
2. **回落路径**：若合并导致有效任务数下降，或负载、尾波和固定开销使收益不成立，
   按 workload 评估更小的 `B_M` 或按行 FullLoad。
3. **单双缓冲是选择题**：每核 tile 数 ≥ 2 且核数不减少时才值得评估双缓冲（结构性判据，
   非万能阈值）；深度计入 `copies` 后 `B_M_max` 需重算。
4. **dtype/精度**：多行合并不改变单行统计语义（统计仍逐行、fp32 累加策略不变）；
   dtype 改变输入、输出和统计缓冲的字节数及对齐需求，从而改变 `B_M_max`，
   可能改变该候选是否可行。
