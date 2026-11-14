# Norm 类与融合：统计 → 保留/重读/重算 → 输出

> **适用**：按行统计归一化（Norm 类：沿行归约统计，再按行归一化输出）及其融合
> （融合 residual 输入、后处理激活、量化 trait 等）。generic 设计方法，
> 不针对具体专有算子，不含任何具体产品算子的实测答案。
>
> 3.0.0-experimental 新增。本文是**设计方法**：策略优劣必须按目标 workload 评估，
> 无实测结论。文中平台常数（对齐字节数等）为示例值，需平台查询回填。

---

## 一、统计阶段

- **统计量由归一化定义决定**：mean/var 类需要 sum/sumsq；max/shift 类需要 max 与 sum(exp) 等。
  归约轴、广播/配对关系、分组（量化组）在语义归一化阶段确定，tiling 只能在其下切分。
- **统计必须覆盖完整 R**：分段统计时，各段统计量按可合并的合并律合并——
  sum/sumsq 直接相加；max 取最大；softmax 类 `m = max_s(m_s)`、
  `l = sum_s(l_s * exp(m_s - m))`（数值稳定的合并示意，边界如 mask/全无效行遵循算子定义）。
- **epsilon 的位置**由归一化定义决定（如分母 `rsqrt(var + eps)`），属于算子语义，tiling 不得改变。
- **累加 dtype**：通常 fp32；转换顺序为 输入 dtype → fp32 累加 → 统计量。
  fp32 中间是物理 buffer，必须入账（见第四节）。
- 流式两个相关统计量（如 mean/var 单遍更新）可用 Welford，见 [Welford 算法详解](alg-welford.md)。

---

## 二、中间阶段（三选一）

统计完成后到输出生成之间，整行中间数据有三种合法组织。符号口径：带 `_b` 的是**单行**对齐后
字节数；`inBytes / fInBytes_i / midBytes / outBytes / out2Bytes` 是**每元素**字节数
（见 `x_b` 定义——单行字节数要乘归约长度 `R`）；GM 流量列按"每元素口径 × R"给出。

```text
x_b    = align_up(R * inBytes, alignBytes)      # 输入行
f_b(i) = align_up(R * fInBytes_i, alignBytes)   # 融合输入 i（如 residual），各一份
mid_b  = align_up(R * midBytes, alignBytes)     # 需要跨阶段保存的中间（如残差和）
out_b  = align_up(R * outBytes, alignBytes)     # 归一化输出
out2_b = align_up(R * out2Bytes, alignBytes)    # 融合第二个输出（可选）
P_b    = 参数驻留（gamma/beta/scale 等，按对齐块计）
stats_b= 统计量驻留
copies = queue 槽位深度 × 每槽份数
```

| 组织 | 做法 | UB 峰值（符号） | GM 流量（每元素口径 × R） | 适用与代价 |
|------|------|------------------|------------|------------|
| **(a) 保留** | 整行（含融合输入）驻留 UB，统计后直接算输出 | `copies*(x_b + Σf_b) + P_b + stats_b + copies*(out_b [+ out2_b])` | `R*(inBytes + ΣfInBytes + outBytes [+ out2Bytes]) + pad`（一遍读，一至两份写；`pad` 为对齐/DMA 实际口径，另列） | 账本放得下才可行；同步最少 |
| **(b) 重读** | 第一遍分段统计；第二遍按 D 段**重读 GM 中已有的数据**，用保留统计量算输出。GM 中已有的量优先直接重读：常见形态是**直接重读原始 x**（GM 本来就有，无需写回任何中间量）；只有第二遍需要的量不是原输入（如融合残差和）才写回中间再读 | 常驻分配总和与可复用峰值**分开列**：`max(统计遍, 输出遍)` **仅当**两遍工作集确为同一队列的同一批物理槽位（合法同槽复用）时成立；否则入账取**两遍之和**。注意：`FreeTensor` 只归还队列槽位状态/事件（bufUsedCount），**不把独立 `InitBuffer` 的物理 UB 容量还给池**，不能作为按 max 记账的释放依据；`pipe Reset` 也必须证明同步与真实重新初始化语义后方可按重初始化后的占用记账。输出遍：`copies*(seg_b [+ segMid_b]) + stats_b` | 直接重读原输入：`R*(2*inBytes + ΣfInBytes + ΣoutBytes) + pad`；写回中间再读：`R*(inBytes + ΣfInBytes + midBytes(写) + midBytes(读) + ΣoutBytes) + pad`。重读/写回按实际元素数计；`P_b`（gamma 等）按真实每核/每 tile/每行加载次数另列 | 不写中间时账本与流量最省；**重读的读次数与 GM 流量计入成本** |
| **(c) 重算** | 第二遍从 UB 内**保留的输入段**重算（段内可重算、不重读 GM） | 介于 (a)(b) 之间：需保留可重算的输入段 | `R*(inBytes + ΣfInBytes + ΣoutBytes) + pad`（一遍读） | 多花重算指令省 GM 流量；输入段也要丢弃时退化为 (b) |

- 三选一是**可行性与成本问题**：账本判可行性，成本按 workload 比较，无默认答案、无固定切换阈值。
- 融合增量必须进入 (a) 的驻留账本：融合输入各占一份物理 buffer，`Σf_b` 不是免费的。
- **账本口径**：InitBuffer/队列槽位的常驻分配不随逻辑阶段消失；"按逻辑阶段取 max"
  必须附**同队列同物理槽复用**的证据，否则按常驻总和入账；`FreeTensor` 归还的是
  逻辑 tensor 与队列槽位状态，不是独立 InitBuffer 的物理容量
  （[../common/resource-lifetime.md](../common/resource-lifetime.md) 第二节唯一计数）。
- 分段（SplitD）执行细节与 chunkCols 公式见 [ar-colsplit.md](ar-colsplit.md)；
  跨阶段数据写回/重读的生命周期口径见 [../common/resource-lifetime.md](../common/resource-lifetime.md)。

---

## 三、输出阶段

- 归一化输出按 D 段生成：每段 `y = (x [+ residual]) * 统计量衍生量 [* gamma] [+ beta]`
  （具体公式由算子定义决定；此处只强调**输出按段索引驱动，不得重复或遗漏**）。
- 融合的第二个输出（如 residual 加法结果）与统计量输出（如 rstd/mean）分别写回各自的 GM 张量；
  写回组织（逐行标量 / 攒块搬出）见 [ar-fullload.md](ar-fullload.md) 4.2。
- **唯一写者原则**：任一 GM 位置只被一个核、一个阶段写入；跨核/跨阶段的
  read-modify-write 或多写者需要额外的拆分与同步设计，不是默认合法。
- 输出段的 padding 语义遵循算子定义；padding 值不得污染统计量（见第六节边界清单）。

---

## 四、融合资源账本（物理字节）

统一按物理字节计，逐项列全：

```text
reserveBytes + Σ_i ( align_up(bytes_i, alignBytes) × copies_i ) ≤ ubSize
```

清单（Norm + 融合的典型项，按分支取舍）：

| 项 | 说明 |
|----|------|
| 融合输入 | 各一份物理 buffer（x、residual、…），`copies_i` 各自计 |
| fp32 统计/中间 | 统计量驻留 `stats_b`、升精度整行 fp32 中间（若分支需要） |
| 参数驻留 | gamma/beta/scale 等 R 长参数，一次载入多 tile 复用 |
| 输出 | 归一化输出一份；融合第二输出一份（如适用） |
| 队列深度 | 每个 queue 的 depth × 每槽字节数；深度 2 只是必要条件，不证明重叠（[../common/resource-lifetime.md](../common/resource-lifetime.md)） |
| 对齐 | 每项 buffer 按 `alignBytes` 上取整；`reserveBytes` 含对齐补齐与其他常驻 |

**参数驻留与行合并争抢同一 UB 预算**：`B_M` 增大时行足迹 `B_M * rowFootprint` 线性放大，
参数驻留不变但占比上升；两者共同消耗同一 `ubSize - reserveBytes`，
多行合并的 `B_M` 上限公式见 [ar-merge-row.md](ar-merge-row.md)（其 `rowFootprint`
在融合场景要把 `Σf_b` 计入）。

---

## 五、参数求解骨架

按顺序求解，任何一步不可行就回退上一步改变组织：

```text
1. 整行可行性（含融合增量）
   copies*(x_b + Σf_b) + P_b + stats_b + copies*(out_b [+ out2_b]) + tmpBufSize
     ≤ ubSize - reserveBytes ?
   ├─ YES → rowFactor / B_M（多行合并上限公式见 ar-merge-row.md）
   └─ NO  → 核内 D 分段（ubLoop / chunkCols 公式见 ar-colsplit.md 2.2，
            融合增量并入 statsBytes/reserveBytes 口径），中间阶段按第二节三选一
2. 核间任务：按行分核（rowsPerCore = ceil_div(M, P)）或行组全局分发（Q = ceil_div(M, B_M)），
   两种结构的差异见 ar-merge-row.md
3. 尾块与有效元素守卫：尾核 valid 行、尾块 lastChunkSize、padding 不入统计
4. 混合 dtype 分别计字节：fp16 输入 + fp32 中间 + fp16/quant 输出时，
   inBytes / midBytes / outBytes 各自代入，逐 buffer 对齐（方法见 ../elewise/tiling.md 第六节）
```

---

## 六、语义/精度约束与边界清单

**语义/精度约束**：

- epsilon 位置、归一化公式、统计域由算子语义给定，tiling 不得改变。
- 累加顺序由分段方式决定：分段统计的合并顺序会影响浮点结果，
  属数值设计约束（须满足精度契约），不是可随意调的 tiling 自由度。
- 分段输出不得重复或遗漏（段边界由 tiling 参数唯一决定）。
- **量化 trait 不改变统计域边界**：量化组边界先于 tiling 决定（组是统计域语义），
  tiling 不能改组语义、不能把跨组元素并进同一次统计；量化参数/scale 的处理按各自量化资料。

**边界条件清单**：

| 边界 | 要点 |
|------|------|
| D 未对齐 | UB 内行距用 `rLengthAlign`，搬运/统计 count 用有效 `R`（ar-fullload.md 3.3 口径） |
| M=1 | 无行间并行；单行基线 + 是否跨核归约属可选条件策略（patterns.md S5） |
| 超长 D | 整行不可行 → 核内 SplitD（ar-colsplit.md），中间阶段三选一 |
| 尾块 | `lastChunkSize` / 尾核 `valid` 行；空槽守卫，不读写越界 |
| padding 语义 | pad 值不参与统计（padValue=0 对 sum 无影响、对 max 有影响），输出 pad 区域按算子定义 |

---

## 七、声明

- 本文是设计方法与公式骨架，**不含实测结论**；保留/重读/重算、单/双缓冲、
  行合并与否都按目标 workload 评估后决定。
- 融合 trait（量化等）按各自专项资料处理；本文只约束它们**不改归约/统计语义、
  必须入资源账本**这两点。
- 相关文档：[ar-fullload.md](ar-fullload.md)（单行全载）、[ar-colsplit.md](ar-colsplit.md)
  （核内 SplitD 与三组织）、[ar-merge-row.md](ar-merge-row.md)（多行合并）、
  [tiling-fields.md](tiling-fields.md)（字段与 tmpBuf）、
  [../common/resource-lifetime.md](../common/resource-lifetime.md)（物理生命周期与守卫）。
