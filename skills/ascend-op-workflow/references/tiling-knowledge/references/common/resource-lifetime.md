# 物理资源生命周期与容量账本（跨类别公共能力）

> **适用**：所有算子类别的 UB/GM 账本、队列与事件容量、多核任务口径。
> 本文件是知识侧（K）的资源生命周期真源；各算子类别的 tiling 文档引用本文，
> 不重复推导。
>
> 3.0.0-experimental 新增。本文不含平台容量数值：所有容量、深度、事件 ID 空间
> 以**目标环境**的 SDK 与平台查询为准（见第三节）。

---

## 一、物理分配 vs 逻辑名

- 逻辑 tensor 名（`xLocal`、`tmpBuf`…）不等于物理槽位。多个逻辑名指向同一物理槽位的
  **合法复用**必须同时满足：生命周期不重叠，且无跨同步域的读写冒险。
- **"最后一次使用"不等于"已释放"**：队列槽位 / pipe buffer 在 pipe 生命周期结束前一直占用。
  账本**不能**因为"逻辑上不再读取"而扣除某块物理占用。
- **`FreeTensor` 不是物理 UB 释放**：SDK 层 `FreeTensor→FreeBuffer` 只归还队列槽位
  状态/事件与 bufUsedCount，不下调独立 `InitBuffer` 分配的物理池水位（pool.maxAddr）。
  只有**同一队列同一物理槽**的复用才能在账本中取 max；独立 `InitBuffer` 的多块分配
  即使各自 `FreeTensor`，峰值仍按同时存在的物理分配总和计。`pipe Reset` 按重初始化
  语义记账前必须证明同步与真实重新初始化。
- 推论：跨阶段驻留量（如 SplitD 的统计量、Norm 融合的参数驻留）从分配到最后一阶段
  结束全程入账；写回 GM 的中间量在重读完成前，其 GM 侧副本也不可被他人覆写（唯一写者）。

## 二、Buffer 计数与队列深度

`copies`（同一数据的物理份数）按**真实物理分配唯一计数**：先逐行列出物理分配
（每个队列槽位、每个独立 `InitBuffer`/`TBuf`、每个独立 tmpBuf），同一物理槽位
只计一次；只有独立于队列槽的额外物理 buffer 才加项。

```text
正确口径示例：
  queue depth = 2 的双缓冲（两槽各存一份）        → copies = 2
                                                  （不得再加"double buffer 第二份"）
  queue depth = 2，且另有独立常驻副本一份         → copies = 3（独立物理分配才加）
  临时 / 中间 buffer（fp32 累加、统计、scratch）   → 独立列项，逐个物理分配入账

双算反例（虚增）：depth=2 又加"双缓冲第二份" → copies=3；
  tile/ubFormer 等以 copies 为除数的量被多除一次，可行性被低估、tile 偏小。
漏算反例（虚减）：同一 TBuf 的两个逻辑名当两份计入再"复用"扣回、
  或把 InitBuffer 常驻量按逻辑阶段取 max（见 [../reduction/norm-fusion.md](../reduction/norm-fusion.md) 第二节）
  → 账本小于真实峰值占用。
```

- **深度 2 只是必要条件，不证明搬运与计算重叠**：还需要循环结构与事件配对支撑。
  账本上深度计入占用；性能上不因开了 double buffer 就宣称已流水。
- **单缓冲 / 双缓冲是选择题**，无万能阈值。可用的结构性判据（示例，非规则）：
  每核 tile 数 ≥ 2 且切换后核数不减少，才值得评估双缓冲；深度翻倍会挤占 tile 尺寸
  （如 elewise 的 `maxElemNum`、ColSplit 的 `chunkCols`、MergeN 的 `B_M` 都以 copies 为除数），
  切换后必须重算可行性。
- scratch / 库 API 暂存（`Get*MaxMinTmpSize` 类查询结果）同样入账，见 [../reduction/tiling-fields.md](../reduction/tiling-fields.md)。

## 三、Queue / event 容量的取证方式（不得硬编码万能上限）

- 设备侧 `TQue`/`TBuf` 的深度与数量上限、事件（flagId）空间、pipe 数量，
  **以目标环境安装的 CANN SDK 头文件与文档为准**
  （例如 `<ASCEND_HOME_PATH>/include/ascendc/` 下的 basic_api/interface 与 pipe/同步资料）。
- 不同平台/版本的事件 ID 空间、队列槽数、pipe 数**不同**：每个任务必须查**本轮** SDK
  与平台资料，禁止把某一平台的数值写成本 skill 的通用常数。
- "不同生命周期事件必须使用不同 flagId"及平台相关的事件 ID 规则，
  FlashAttention 设计资料有完整记录，见 [../flashattention/implementation_ref.md](../flashattention/implementation_ref.md)。
- 取证方法示例（不是容量结论）：本地 2026-10 观察到 CANN toolkit 9.2.0 CPU 容器
  仅保留 acl host 侧头文件，ascendc kernel 侧头文件需在目标环境查询——
  即"本地查不到"本身就是一条必须记录的取证结果，应触发向目标环境取证，而不是填一个假设值。

## 四、活跃块 vs 启动块 vs 物理执行单元

- `launch_blocks`（逻辑启动块，可多波）≥ **活跃块数**（分到非空工作的块数）。
  两者都要入账：空块也要走启动/同步路径，但无产出。
- 物理 AIV / 核心数由平台查询；任务数 Q、每核任务数 `ceil_div(Q, P)`、尾波
  （最后一波可能只有少量任务）是三个不同的数，账本与性能分析分开记。
- MIX（AIC/AIV）场景：AIC 与 AIV 的块数、buffer、事件**分别计数，不得混用**。

## 五、整数溢出与尾块

统一规则：元素数/字节数统一 `int64`；多核偏移计算用 64 位；对齐上取整先在宽类型中完成；
尾块循环以**有效长度**为界。定义（与 [../elewise/tiling.md](../elewise/tiling.md) 第一节一致）：

```text
ceil_div(x, a) = (x + a - 1) / a          // x ≥ 0, a ≥ 1
align_up(x, a) = ceil_div(x, a) * a
```

反例（错误写法 → 后果 → 正确写法；均可用 CPU 单测按给定向量复现。
示例用 int32 以便在小类型上复现溢出，生产 tiling 用 int64 时失败模式相同、只是阈值更远）：

| # | 错误写法 | 后果 | 正确写法 |
|---|---------|------|---------|
| 1 | `(a + b - 1) / b` 求 ceil | `a + b - 1` 溢出。测试向量：`a = 2147483647, b = 4096`：`a + b - 1 = 2147487742` 超出 int32（C++ 未定义行为，典型二进制回绕为 `-2147479554`），除法得 `-524287`；正确值是 `524288` | `a > 0 ? 1 + (a - 1) / b : 0`（同向量得 `1 + 524287 = 524288`）。注意 `a = 0` 必须单独归零：`1 + (0-1)/b` 在 C++ 向零截断下得 `1`，会把空任务多算一块 |
| 2 | `align_up(x, a) = (x + a - 1) / a * a` 直接在窄类型算 | 两处溢出：加法同反例 1；且**合法输入的对齐结果本身**可能超出类型上限。测试向量：`x = 2147483647, a = 32` → 正确对齐值 `2147483648 > INT32_MAX`，静默截断成负数 | **先提升操作数再相加**：`((int64_t)x + (int64_t)a - 1) / a * a`。注意 `(int64_t)(x + a - 1)` 是错的——加法已在窄类型中发生，事后转宽救不回溢出。`x` 已是 int64 时改用除余避免加法溢出：`q = x / a; r = x % a; align = r ? q * a + a : x;`，并显式检查 `q * a + a` 及最终结果可表示；结果超目标类型上限时按"本分支不可行"回资源账本处理，不得截断。`align_up(0, a) = 0` |
| 3a | 尾块仍按 `blockFormer` 循环 | 越界读写。测试向量：`dim0 = 5000, blockFormer = 512` → `blockNum = ceil_div(5000,512) = 10`，`blockTail = 5000 - 9*512 = 392`；尾块若循环 512 次，访问 idx 4608..5119，其中 ≥ 5000 越界 | `valid = isLastBlock ? blockTail : blockFormer;` 循环与搬运都按 `valid`（MergeN 的空行槽、ColSplit 的 `lastChunkSize` 同理） |
| 3b | `int32_t off = blockIdx * blockFormer * elemBytes` | 32 位溢出（C++ 未定义行为，典型回绕）成负偏移。测试向量：`blockFormer = 524288, elemBytes = 4, blockIdx = 1024` → 真值 `2147483648` 超出 int32，典型回绕为 `-2147483648` | `int64_t off = (int64_t)blockIdx * blockFormer * elemBytes;`（乘法链中先提升到 int64） |

尾块守卫的通用形式：

```cpp
int64_t valid = (blockIdx == blockNum - 1) ? (total - (blockNum - 1) * blockFormer)
                                           : blockFormer;   // 1 ≤ valid ≤ blockFormer（total > 0 时）
for (int64_t i = 0; i < valid; ++i) { /* 只处理有效元素 */ }
```

## 六、在原设计和审查中使用

资源公式落实到原设计及实际 Host/Device 代码，在原实现审查中核对；平台事实以目标版本官方资料和实际平台接口为准。具体核对见 [shape 选型方法](shape-selection.md#设计与实现核对)，不依赖额外方案或实现描述文件。

## 跨类别引用

| 使用方 | 文档 |
|--------|------|
| EleWise 字节账本与对齐 | [../elewise/tiling.md](../elewise/tiling.md) |
| AR 全载（R_max 与队列生命周期） | [../reduction/ar-fullload.md](../reduction/ar-fullload.md) |
| ColSplit（统计量跨阶段驻留） | [../reduction/ar-colsplit.md](../reduction/ar-colsplit.md) |
| MergeN（B_M 账本） | [../reduction/ar-merge-row.md](../reduction/ar-merge-row.md) |
| Norm 融合（三阶段驻留） | [../reduction/norm-fusion.md](../reduction/norm-fusion.md) |
| Pooling（窗口块账本） | [../pooling/patterns.md](../pooling/patterns.md) |
## 七、DMA 字段宽度与单位口径（静态证据类）

Host/Device 边界上每个 tiling 字段都有**位宽**：Device 侧按声明类型解释字段，Host 侧数值即使
合法，超宽也会在 Device 侧截断回绕。例：某 `.asc` 实现 LoadGamma 以 `uint16` 承载 `H*2`，
`H=32768` 时 `H*2=65536` 截断为 0——Host resolver 与 Device 对同一 shape 的理解从此分叉。
此类缺陷由**静态源码/公式审查**发现，属于静态证据类；未经目标板实验不得宣称某个已测 fullLoad
用例证明了任意 H 的安全性。

因此资源证明必须包含：

- 每个 DMA/tiling 字段的类型、单位（元素数还是字节数）与位宽；乘法系数（如 `H*2`）在
  **参与运算前**是否已提升位宽。
- 截断/上界检查：`字段最大可表示值 >= 本分支最大真实值`，超出时按"本分支不可行"回资源账本
  处理。
- 超宽 shape 的 chunking 组织：按位宽安全地把大维度拆分为多个字段内可表示的子块。
- 字段位宽示例：uint16 无法表示 65536；乘法前转宽，并按目标字段上限检查后分块。
