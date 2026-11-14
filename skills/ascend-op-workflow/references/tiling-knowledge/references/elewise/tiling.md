# EleWise - Tiling 详细计算

> **适用场景**: 输入输出 Shape 完全相同，逐元素独立计算
>
> 本文所有平台常数（对齐字节数、每核最小数据量等）均为**示例值**，不是权威查询结果；
> 实际任务必须用平台查询（`npu-arch` / platform_ascendc query）回填。
> 所有 worked example 使用合成数值，只验证公式本身。

---

## 〇、符号与约定

| 符号 | 含义 |
|------|------|
| `elemBytes` | 该分支的元素字节数（int8=1、fp16/bf16=2、fp32=4） |
| `minDtypeBits` | `minDtypeBits = elemBytes * 8`（**模板参数**，由该分支支持的最小 dtype 决定，如 int8=8、fp16=16；不是全局常量） |
| `reserveBytes` | 本分支为参数/对齐/其他常驻 buffer 预留的字节数，**来自资源账本**，不能凭空填 0 |
| `alignBytes` | UB 块对齐字节数，平台查询值（**示例取 32 或 256**，本文示例统一取 32） |
| `alignFactor` | `alignFactor = alignBytes / elemBytes`（每个对齐块容纳的元素数）。要求 `elemBytes` 整除 `alignBytes` 的平台才可用此简化式；否则按 `align_up` 逐 buffer 计算 |
| `bufferNum` | 该统计阶段同一数据的物理份数（queue 槽位深度 × 每槽份数等，见 [../common/resource-lifetime.md](../common/resource-lifetime.md)） |

整数运算约定（全文件统一，公式按此可被 CPU 单测复现）：

```text
floor_div(x, a)  = x / a                    // C++ 整数除法，x ≥ 0, a ≥ 1
ceil_div(x, a)   = (x + a - 1) / a          // x ≥ 0, a ≥ 1；溢出改写见 ../common/resource-lifetime.md
align_up(x, a)   = ceil_div(x, a) * a       // 结果 ≥ x；对齐结果本身也可能超出原类型上限
```

- 元素数/字节数统一 `int64`（溢出与反例见 [../common/resource-lifetime.md](../common/resource-lifetime.md)）。
- 本文"元素数"均指有效元素数；UB 内的物理占用按对齐后字节数计。

---

## 一、多核切分（blockFormer / blockNum）

### 核心思想

按对齐**字节数**做核间切分，并保证每核数据量不低于一个工程经验下限（经验值，可按任务调整，不是平台约束）。

> 单位约定：核间对齐用字节描述（`BLOCK_ALIGN_BYTES`），其元素数等价
> `blockAlignElems = BLOCK_ALIGN_BYTES / elemBytes` **随 dtype 变化**
> （fp16 → 256 元素、fp32 → 128 元素）。旧文档"对齐到 512 元素"的写法只在
> `elemBytes = 1`（int8）时与"512 字节"等价，两者不能混用。

### Tiling 参数说明

| 参数 | 含义 | 计算公式 |
|------|------|---------|
| `dim0` | 元素总数量 | 所有维度相乘 |
| `coreNum` | 实际使用的核数 | `min(ceil_div(dim0 * elemBytes, MIN_TILE_BYTES_PER_CORE), availableCoreNum)` |
| `blockAlignElems` | 核间对齐的元素数等价 | `BLOCK_ALIGN_BYTES / elemBytes`（要求 elemBytes 整除） |
| `blockFormer` | 每个核的基础元素数（对齐后） | `align_up(ceil_div(dim0, coreNum), blockAlignElems)` |
| `blockNum` | 虚拟 block 数量 | `ceil_div(dim0, blockFormer)` |
| `blockTail` | 尾 block 的有效元素数 | `dim0 - (blockNum - 1) * blockFormer` |

### 计算步骤

```cpp
// 常量：示例值，需平台查询/按任务确认
constexpr int64_t MIN_TILE_BYTES_PER_CORE = 4096;  // 每核最少字节数（工程经验值）
constexpr int64_t BLOCK_ALIGN_BYTES = 512;         // 核间对齐字节数

// Step 1: 计算核数（字节口径；与 bits 口径 min(ceil(dim0*minDtypeBits/8/MIN), N) 等价）
coreNum = min(ceil_div(dim0 * elemBytes, MIN_TILE_BYTES_PER_CORE), availableCoreNum);
if (coreNum < 1) coreNum = 1;

// Step 2: 每核基础元素数，按对齐字节数换算的元素数对齐
blockAlignElems = BLOCK_ALIGN_BYTES / elemBytes;
blockFormer = align_up(ceil_div(dim0, coreNum), blockAlignElems);

// Step 3: 虚拟 block 数量与尾块
blockNum = ceil_div(dim0, blockFormer);
blockTail = dim0 - (blockNum - 1) * blockFormer;   // blockNum ≥ 1 时必有 1 ≤ blockTail ≤ blockFormer
```

> `dim0 = 0` 时不产生任何 block，直接走空 tensor 出口；`dim0 > 0` 时 `blockNum ≥ 1` 且尾块非空。

### 核间数据偏移

```cpp
// 字节偏移必须用 int64：blockFormer * blockIdx * elemBytes 在大 shape 下会超出 32 位
template <typename DataType>
__aicore__ inline int64_t CalcBlockOffset() {
    return (int64_t)blockFormer * GetBlockIdx() * sizeof(DataType);
}
```

### Worked example（合成数值）

`dim0 = 100000`，`elemBytes = 2`（fp16），`availableCoreNum = 40`，
`MIN_TILE_BYTES_PER_CORE = 4096`，`BLOCK_ALIGN_BYTES = 512`：

- `coreNum = min(ceil_div(200000, 4096), 40) = min(49, 40) = 40`
- `blockAlignElems = 512 / 2 = 256` 元素
- `ceil_div(100000, 40) = 2500`；`blockFormer = align_up(2500, 256) = 10 * 256 = 2560`
- `blockNum = ceil_div(100000, 2560) = 40`（39 个整块 = 99840）
- `blockTail = 100000 - 39 * 2560 = 160`（有效元素，最后一块只处理 160 个）

---

## 二、UB 切分（ubFormer / ubLoop / tail）

### 核心思想

单次进入 UB 的元素数由**字节口径**的资源账本决定，再按对齐元素数向下取整。
可行性（放不放得下）由账本判定；账本放得下不代表该 tile 大小最优（最优性需按 workload 比较）。

### 标准形式（canonical，bytes）

```text
maxElemNum = (ubSize - reserveBytes) / (bufferNum * elemBytes)      // floor_div，bytes / (bytes/elem)
ubFormer   = floor_div(maxElemNum, alignFactor) * alignFactor       // 向下取整到对齐元素数
```

若需要 bits 口径，只能是下面这个**代数等价**形式（`minDtypeBits = elemBytes * 8`，
分子分母同乘 8 不改变整数商）：

```text
maxElemNum = (ubSize - reserveBytes) * 8 / (bufferNum * minDtypeBits)   // 与上式结果相同
```

旧写法 `maxElemNum = (ubSize - extraSize) * 8 / (bufferNum * elemBytes)` 中
`ubSize`/`extraSize` 是字节、`bufferDivisor = bufferNum * elemBytes` 是"字节/元素"，
再乘 8 即把 bits 与 bytes 混用，结果被放大约 8 倍，是错误公式。
`reserveBytes`（本分支为参数/对齐/其他常驻 buffer 预留的字节数，来自资源账本）
与旧文的 `extraSize` 是同一概念，全文统一用 `reserveBytes`。

### 对齐闭式与定义式

`ubFormer` 的**定义式**（唯一权威，任何平台都可测）：

```text
ubFormer_max = max{ T : bufferNum * align_up(T * elemBytes, alignBytes) ≤ ubSize - reserveBytes }
```

当 `elemBytes` 整除 `alignBytes` 时，它有闭式解，且与"先 floor 再向下取整"两步式结果相同：

```text
ubFormer_max = floor_div(ubSize - reserveBytes, bufferNum * alignBytes) * alignFactor
             = floor_div(floor_div(ubSize - reserveBytes, bufferNum * elemBytes), alignFactor) * alignFactor
```

`elemBytes` 不整除 `alignBytes` 的平台不能用上述简化式，按定义式逐 buffer `align_up` 求解
（约束关于 T 单调，可从无对齐上界向下收缩）。

### 计算步骤

```cpp
// Step 1: UB 能容纳的最大元素数（bytes 口径）
int64_t maxElemNum = (ubSize - reserveBytes) / (bufferNum * elemBytes);
if (maxElemNum <= 0) { /* 分支不可行：工作集放不下任何元素，回到资源账本检查 reserveBytes/bufferNum */ }

// Step 2: 按对齐元素数向下取整（elemBytes 整除 alignBytes 时与闭式一致）
int64_t alignFactor = alignBytes / elemBytes;
ubFormer = (maxElemNum / alignFactor) * alignFactor;

// Step 3: 循环次数（显式 ceil_div / floor）
ubLoopOfFormerBlock = ceil_div(blockFormer, ubFormer);
ubTailOfFormerBlock = blockFormer - (ubLoopOfFormerBlock - 1) * ubFormer;
```

### Worked example A（对齐不咬合）

合成值：`ubSize = 65536`，`reserveBytes = 0`，`bufferNum = 2`，`elemBytes = 2`，`alignBytes = 32`：

- `maxElemNum = 65536 / (2 * 2) = 16384`
- `alignFactor = 32 / 2 = 16`；`ubFormer = floor_div(16384, 16) * 16 = 16384`
- 闭式核对：`floor_div(65536, 2 * 32) * 16 = floor_div(65536, 64) * 16 = 1024 * 16 = 16384` ✓
- 物理核对：每份 `16384 * 2 = 32768` 字节 = `1024 * 32`（已 32 对齐），两份共 `65536 = ubSize`，恰好都放得下 ✓

### Worked example B（对齐咬合）

合成值：`elemBytes = 4`，`bufferNum = 3`，`ubSize = 10000`，`reserveBytes = 0`，`alignBytes = 32`：

- 无对齐上界：`maxElemNum = floor_div(10000, 3 * 4) = 833`（余 4）
- 833 个元素每份 `833 * 4 = 3332` 字节；`align_up(3332, 32) = 105 * 32 = 3360`
  （注意：`align_up` 必须向上，`104 * 32 = 3328 < 3332` 不是合法对齐值）
- 三份对齐后共 `3 * 3360 = 10080 > 10000`，**上界 833 不可用**
- 闭式：`floor_div(10000, 3 * 32) * (32 / 4) = floor_div(10000, 96) * 8 = 104 * 8 = 832`
- 两步式核对：`floor_div(833, 8) * 8 = 104 * 8 = 832` ✓ 与闭式一致
- 物理核对：832 × 4 = 3328 = `104 * 32`（对齐），三份共 `9984 ≤ 10000` ✓；
  833 → `3 * 3360 = 10080 > 10000` ✗。故最大对齐 tile = **832** 元素。

---

## 三、Kernel 执行模型

### Process 循环结构

**核心逻辑**：区分首 block 和尾 block，因为它们的 UB 循环次数可能不同。
循环/尾部次数全部由第二节的显式 `ceil_div`/`floor` 公式给出：

```text
ubLoopOfFormerBlock = ceil_div(blockFormer, ubFormer)
ubTailOfFormerBlock = blockFormer - (ubLoopOfFormerBlock - 1) * ubFormer     // 1 ≤ ubTail ≤ ubFormer
ubLoopOfTailBlock   = ceil_div(blockTail, ubFormer)
ubTailOfTailBlock   = blockTail - (ubLoopOfTailBlock - 1) * ubFormer
```

```cpp
// 1. 判断当前处理的是否是最后一个 block
bool isLastBlock = (blockIdx == blockNum - 1);

// 2. 获取当前 block 的循环次数和尾部大小
//    首 block 和尾 block 的循环次数/尾部大小可能不同
loopNum = isLastBlock ? ubLoopOfTailBlock : ubLoopOfFormerBlock;
tailNum = isLastBlock ? ubTailOfTailBlock : ubTailOfFormerBlock;

// 3. 主循环（处理完整的 UB 块）
for (uint64_t i = 0; i < loopNum - 1; i++) {
    ProcessTile(offset, ubFormer);
    offset += ubFormer;
}

// 4. 尾部处理（处理最后一个不完整的 UB 块，只处理 tailNum 个有效元素）
ProcessTile(offset, tailNum);
```

**为什么要区分首/尾 block？**

- `blockFormer` 是按对齐元素数向上取整的，可能大于均分值
- 最后一个 block 的有效数据量 `blockTail` 可能小于 `blockFormer`
- 因此 `ubLoopOfFormerBlock` ≠ `ubLoopOfTailBlock`、`ubTailOfFormerBlock` ≠ `ubTailOfTailBlock` 可能同时发生

Worked example（接第一节示例）：`blockFormer = 2560`，`blockTail = 160`，设 `ubFormer = 1024`（合成值）：

- 首块：`ubLoopOfFormerBlock = ceil_div(2560, 1024) = 3`；`ubTailOfFormerBlock = 2560 - 2 * 1024 = 512`
- 尾块：`ubLoopOfTailBlock = ceil_div(160, 1024) = 1`；`ubTailOfTailBlock = 160 - 0 * 1024 = 160`

尾块每次搬运/计算都以 `tailNum` 为有效长度（DataCopyPad 场景 padding 值不参与语义，见本文第六节的 dtype 说明与 [../common/resource-lifetime.md](../common/resource-lifetime.md) 的守卫反例）。

---

## 四、最小可执行 Tiling 模板

```cpp
struct TilingData {
    int64_t dim0;           // 元素总数量
    int32_t coreNum;        // 实际核数
    int64_t blockFormer;    // 每个核的基础元素数（对齐后）
    int64_t blockNum;       // block 数量
    int64_t ubFormer;       // UB 基础大小（元素数，对齐后）
    int64_t ubLoopOfFormerBlock;
    int64_t ubTailOfFormerBlock;
    int64_t ubLoopOfTailBlock;
    int64_t ubTailOfTailBlock;
};

TilingData ComputeTiling(int64_t dim0, int64_t elemBytes, int64_t ubSize,
                         int64_t bufferNum, int64_t reserveBytes,
                         int64_t alignBytes, int64_t availableCoreNum) {
    TilingData tiling{};

    // 常量：示例值，非平台查询结果
    constexpr int64_t MIN_TILE_BYTES_PER_CORE = 4096; // 每核最少字节数（工程经验值）
    constexpr int64_t BLOCK_ALIGN_BYTES = 512;        // 核间切分对齐字节数

    // minDtypeBits = elemBytes * 8：该分支支持的最小 dtype 位宽（模板参数，非全局常量）；
    // bits 口径与 bytes 口径代数等价（见第二节），本模板统一用 bytes 口径

    // 1. 多核切分（bytes 口径）
    int64_t totalBytes = dim0 * elemBytes;            // int64，防溢出
    tiling.coreNum = (totalBytes + MIN_TILE_BYTES_PER_CORE - 1) / MIN_TILE_BYTES_PER_CORE;
    tiling.coreNum = std::min(tiling.coreNum, availableCoreNum);
    if (tiling.coreNum < 1) tiling.coreNum = 1;

    int64_t blockAlignElems = (elemBytes > 0 && BLOCK_ALIGN_BYTES % elemBytes == 0)
                              ? BLOCK_ALIGN_BYTES / elemBytes
                              : 1;                    // 不整除时退化为逐 buffer 对齐，不能套简化式
    int64_t avgPerCore = (dim0 + tiling.coreNum - 1) / tiling.coreNum;
    tiling.blockFormer = (avgPerCore + blockAlignElems - 1) / blockAlignElems * blockAlignElems;
    tiling.blockNum = (dim0 + tiling.blockFormer - 1) / tiling.blockFormer;

    // 2. UB 切分（canonical bytes 形式；elemBytes 须整除 alignBytes 才可用 alignFactor 简化）
    int64_t maxElemNum = (ubSize - reserveBytes) / (bufferNum * elemBytes);
    // maxElemNum ≤ 0 ⇒ 本分支不可行（工作集放不下任何元素），须回资源账本，不可继续计算
    int64_t alignFactor = alignBytes / elemBytes;
    tiling.ubFormer = (maxElemNum / alignFactor) * alignFactor;

    // 3. 循环次数（显式 ceil_div）
    tiling.ubLoopOfFormerBlock = (tiling.blockFormer + tiling.ubFormer - 1) / tiling.ubFormer;
    tiling.ubTailOfFormerBlock = tiling.blockFormer - (tiling.ubLoopOfFormerBlock - 1) * tiling.ubFormer;

    int64_t blockTail = dim0 - (tiling.blockNum - 1) * tiling.blockFormer;
    tiling.ubLoopOfTailBlock = (blockTail + tiling.ubFormer - 1) / tiling.ubFormer;
    tiling.ubTailOfTailBlock = blockTail - (tiling.ubLoopOfTailBlock - 1) * tiling.ubFormer;

    tiling.dim0 = dim0;
    return tiling;
}
```

---

## 五、经验总结

| 经验 | 说明 | 代码模式 |
|------|------|----------|
| **最小粒度** | 每核最少字节数是工程经验值（示例 4KB），用于避免过碎的核间切分；不是平台约束 | `MIN_TILE_BYTES_PER_CORE = 4096` |
| **多核对齐** | 按**字节**对齐（示例 512B），元素数等价 `512 / elemBytes` 随 dtype 变化 | `blockFormer = align_up(ceil_div(dim0, coreNum), BLOCK_ALIGN_BYTES / elemBytes)` |
| **UB 账本** | bytes 口径：`(ubSize - reserveBytes) / (bufferNum * elemBytes)`；reserveBytes 来自资源账本 | `maxElemNum` |
| **UB 对齐** | `alignFactor = alignBytes / elemBytes`（示例 alignBytes=32：fp32→8，fp16→16）；要求 elemBytes 整除 alignBytes | `ubFormer = (maxElemNum / alignFactor) * alignFactor` |
| **跨核偏移** | 当前核 GM 字节偏移 = `blockFormer * blockIdx * elemBytes`，int64 | `CalcBlockOffset()` |

---

## 六、dtype 分支：FP16/BF16 升精度（Add/Sub）的 UB 预算

**何时启用**：[patterns.md](patterns.md) 的 Step 2 判定命中升精度分支时使用。

### 1. Buffer 规划差异

升精度分支在原 dtype Queue 之外，额外引入 **K 份 `ubFormer * sizeof(float)` 的 FP32 中间 Buffer**。K 由 API 层的别名约束决定，tiling 阶段只需将其作为参数代入 UB 预算。

| 项 | 原 dtype 直算 | 升精度分支 |
|---|--------------|-----------|
| 输入/输出 Buffer dtype | 原 dtype（half/bf16） | 原 dtype（不变） |
| FP32 中间 Buffer 份数 | — | **K**（由 API 别名约束给出） |
| 单份 FP32 中间大小 | — | `ubFormer * sizeof(float)` |
| 总 UB 占用（无对齐口径） | `bufferNum * ubFormer * elemBytes` | `bufferNum * ubFormer * elemBytes + K * ubFormer * sizeof(float)` |

### 2. ubFormer 计算调整

混合 dtype 下**对齐项不可省略**（旧写法 `(ubSize * 8) / bufferDivisor` 同样混用了 bits/bytes）。
约束的定义式为：

```text
bufferNum * align_up(T * elemBytes, alignBytes) + K * align_up(T * sizeof(float), alignBytes)
    ≤ ubSize - reserveBytes
```

求解骨架（host 侧一次计算，可复现）：

```cpp
// Step 1: 无对齐上界（只是上界，可能不可行）
int64_t divisor = bufferNum * elemBytes + K * sizeof(float);
int64_t tUpper = (ubSize - reserveBytes) / divisor;

// Step 2: 从上界向下逐 1 收缩（约束关于 T 单调不增，可二分；线性收缩最坏 tUpper 次循环）
while (tUpper > 0 &&
       bufferNum * AlignUp(tUpper * elemBytes, alignBytes) +
       K * AlignUp(tUpper * (int64_t)sizeof(float), alignBytes) > ubSize - reserveBytes) {
    tUpper--;
}
ubFormer = tUpper;   // tUpper == 0 ⇒ 本分支不可行，回资源账本
```

> 同质单 dtype（`K = 0` 情形）下，第二节的两步式与闭式精确等价；
> 混合 dtype 时因两类 buffer 的对齐余量不同，简单除式**不精确**，必须按定义式收缩。

### Worked example（合成数值）

`bufferNum = 2`，`elemBytes = 2`（fp16 输入），`K = 1`（fp32 中间），
`ubSize = 10000`，`reserveBytes = 0`，`alignBytes = 32`：

- 无对齐上界：`divisor = 2*2 + 1*4 = 8`；`tUpper = floor_div(10000, 8) = 1250`
- 核对 T=1250：fp16 每份 `2500 → align_up = 79*32 = 2528`，两份 `5056`；
  fp32 `5000 → 157*32 = 5024`；合计 `5056 + 5024 = 10080 > 10000` ✗（上界不可行）
- 收缩到 T=1248：fp16 `2496 = 78*32`（已对齐），两份 `4992`；fp32 `4992 = 156*32`，合计 `9984 ≤ 10000` ✓
- 再核对 T=1249：fp16 `2498 → 79*32 = 2528`，两份 `5056`；fp32 `4996 → 157*32 = 5024`；合计 `10080 > 10000` ✗
- 故本例最大 `ubFormer = 1248`，且证明"对齐项省略的上界"会高估。

K 的取值取决于 Compute 阶段选用 API 是否支持 dst/src 别名，该参数由 API 实现细节给出后回填。

> 升精度分支不新增 TilingData 字段，Kernel 侧按 dtype 模板参数静态选择分支即可。具体 Cast/Add/Sub 调用、RoundMode、别名写法等属 API 实现细节，tiling 阶段不涉及。
>
> dtype 提示：同一模板在不同 dtype 下 `elemBytes`、`reserveBytes`（参数驻留）与对齐元素数都会变化，
> `maxElemNum`/`ubFormer` 必须按分支重算；dtype 分支本身不等于调度自适应。
