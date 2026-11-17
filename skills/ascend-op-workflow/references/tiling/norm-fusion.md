# Norm 与融合：统计、保留/重读/重算、输出

适用于按行统计后归一化及residual、激活、量化融合。以下是设计方法和合成示例，不含实测或通用切换阈值，平台常数按目标SDK核实。

## 一、统计阶段

这是算子家族的数据流卡；保留/重读/重算是其中可组合的策略，不另复制正文。短行可结合[Merge-row](ar-merge-row.md)，但必须用本页整行输出和融合足迹代入，不能沿用每行一个标量的纯归约预算。公共资源约束统一见[公共账本](resource-lifetime.md#八跨卡片共用的字节预算)。

- **统计量由归一化定义决定**：mean/var 类需要 sum/sumsq；max/shift 类需要 max 与 sum(exp) 等。
  归约轴、广播/配对关系、分组（量化组）在语义归一化阶段确定，tiling 只能在其下切分。
- **统计必须覆盖完整 R**：分段统计时，各段统计量按可合并的合并律合并——
  sum/sumsq 直接相加；max 取最大；softmax 类 `m = max_s(m_s)`、
  `l = sum_s(l_s * exp(m_s - m))`（数值稳定的合并示意，边界如 mask/全无效行遵循算子定义）。
- **epsilon 的位置**由归一化定义决定（如分母 `rsqrt(var + eps)`），属于算子语义，tiling 不得改变。
- **累加 dtype**：按原精度契约选择，例如 fp32；转换顺序为 输入 dtype → fp32 累加 → 统计量。
  fp32 中间是物理 buffer，必须入账（见第四节）。
- 流式两个相关统计量（如 mean/var 单遍更新）可用 Welford，见 [Welford 算法详解](https://github.com/lanhongsheng/operator-shape-derivation/blob/2619c00f74997b7d4b23ae86a77529ddc5ff0416/skills/ascend-op-workflow/references/tiling-knowledge/references/reduction/alg-welford.md)。

## 二、中间阶段（可组合的成本候选）

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
| **(a) 保留** | 整行（含融合输入）驻留 UB，统计后直接算输出 | `copies*(x_b + Σf_b) + P_b + stats_b + copies*(out_b [+ out2_b])` | `R*(inBytes + ΣfInBytes + outBytes [+ out2Bytes]) + pad`（一遍读，一至两份写；`pad` 为对齐/DMA 实际口径，另列） | 账本放得下才可行；可避免额外 GM 往返，同步仍按实现核算 |
| **(b) 重读** | 第一遍分段统计；第二遍按 D 段**重读 GM 中已有的数据**，用保留统计量算输出。GM 中已有的量优先直接重读：常见形态是**直接重读原始 x**（GM 本来就有，无需写回任何中间量）；只有第二遍需要的量不是原输入（如融合残差和）才写回中间再读 | 按[公共账本](resource-lifetime.md#八跨卡片共用的字节预算)核实同槽复用后才可取两阶段峰值，否则独立分配求和。输出遍：`copies*(seg_b [+ segMid_b]) + stats_b` | 直接重读原输入：`R*(2*inBytes + ΣfInBytes + ΣoutBytes) + pad`；写回中间再读：`R*(inBytes + ΣfInBytes + midBytes(写) + midBytes(读) + ΣoutBytes) + pad`。重读/写回按实际元素数计；`P_b`（gamma 等）按真实每核/每 tile/每行加载次数另列 | 是否写中间按实际输出、重算和流量权衡；**重读的读次数与 GM 流量计入成本** |
| **(c) 重算** | 完整统计完成后，从仍保留且覆盖全部待输出位置的原始输入重算中间量；丢弃了输入的段须重读 | 保留的原始输入、统计、重算暂存和输出均入账；不保证介于 (a)(b) 之间 | `R*(inBytes + ΣfInBytes + ΣoutBytes) + pad`（一遍读；前提是所有待输出位置的原始输入仍可取） | 多花重算指令省中间量驻留；原始输入也已丢弃时须按 (b) 计重读流量 |

三方案先按[公共账本](resource-lifetime.md#八跨卡片共用的字节预算)判可行性，再按workload成本比较；融合输入、升精度中间和API scratch都须入账。同槽复用需证明生命周期合法，不能仅按逻辑阶段取max。分段执行见[归约预算](reduction-budget.md)。

## 三、输出阶段

- 归一化输出按 D 段生成：每段 `y = (x [+ residual]) * 统计量衍生量 [* gamma] [+ beta]`
  （具体公式由算子定义决定；此处只强调**输出按段索引驱动，不得重复或遗漏**）。
- 融合的第二个输出（如 residual 加法结果）与统计量输出（如 rstd/mean）分别写回各自的 GM 张量；
  写回组织（逐行标量 / 攒块搬出）见 [归约预算](reduction-budget.md) 的地址、统计与输出。
- 每个输出段的写入归属、冲突及同步按[公共账本](resource-lifetime.md#八跨卡片共用的字节预算)核对。
- 输出段的 padding 语义遵循算子定义；padding 值不得污染统计量（见第六节边界清单）。

## 四、融合资源账本（物理字节）

按[公共账本的统一字节不等式](resource-lifetime.md#八跨卡片共用的字节预算)代入以下 Norm 特有项，不另维护一套物理计数规则：

清单（Norm + 融合的典型项，按分支取舍）：

| 项 | 说明 |
|----|------|
| 融合输入 | 各一份物理 buffer（x、residual、…），`copies_i` 各自计 |
| fp32 统计/中间 | 统计量驻留 `stats_b`、升精度整行 fp32 中间（若分支需要） |
| 参数驻留 | gamma/beta/scale 等 R 长参数，一次载入多 tile 复用 |
| 输出 | 归一化输出一份；融合第二输出一份（如适用） |
| 队列/对齐 | 统一按公共账本计数；不同输入、中间、输出槽位分别代入 |

**参数驻留与行合并争抢同一 UB 预算**：`B_M` 增大时行足迹 `B_M * rowFootprint` 线性放大，
参数驻留不变，仍会挤占行组容量；两者共同消耗同一 `ubSize - reserveBytes`，
多行合并的 `B_M` 上限公式见 [Merge-row](ar-merge-row.md)（其 `rowFootprint`
在融合场景要把 `Σf_b` 计入）。

## 五、参数求解骨架

按顺序求解，任何一步不可行就回退上一步改变组织：

```text
1. 整行可行性（含融合增量）
   copies*(x_b + Σf_b) + P_b + stats_b + copies*(out_b [+ out2_b]) + tmpBufSize
     ≤ ubSize - reserveBytes ?
   ├─ YES → rowFactor / B_M（多行合并上限公式见 ar-merge-row.md）
   └─ NO  → 核内 D 分段（ubLoop / chunkCols 公式见 reduction-budget.md 的核内分段，
            融合增量并入 statsBytes/reserveBytes 口径），中间阶段按第二节比较保留/重读/重算及其组合
2. 核间任务：按行分核（rowsPerCore = ceil_div(M, P)）或行组全局分发（Q = ceil_div(M, B_M)），
   两种结构的差异见 ar-merge-row.md
3. 尾块与有效元素守卫：尾核 valid 行、尾块 lastChunkSize、padding 不入统计
4. 混合 dtype 分别计字节：fp16 输入 + fp32 中间 + fp16/quant 输出时，
   inBytes / midBytes / outBytes 各自代入，逐 buffer 对齐（方法见 elementwise-budget.md 的混合 dtype 不等式）
```

## 六、语义/精度约束与边界清单

分段统计的合并顺序影响浮点结果，必须满足原精度契约。量化组先于tiling确定，不能跨组统计；scale等细节按量化专项资料处理。完整R、epsilon位置见第一节，输出唯一覆盖见第三、五节。

**边界条件清单**：

| 边界 | 要点 |
|------|------|
| D 未对齐 | UB 内行距用 `rLengthAlign`，搬运/统计 count 用有效 `R`（见 reduction-budget.md 的地址与有效长度） |
| M=1 | 无行间并行；单行基线 + 是否跨核归约属可选条件策略（见 vector-recipes.md 的条件策略） |
| 超长 D | 整行不可行 → 核内 SplitD（见 reduction-budget.md），按实际输入生命周期组合重读与重算 |
| 尾块 | `lastChunkSize` / 尾核 `valid` 行；空槽守卫，不读写越界 |
| padding 语义 | pad 值不参与统计（padValue=0 对 sum 无影响、对 max 有影响），输出 pad 区域按算子定义 |

字段与API scratch的补充定义见[基础tiling字段](https://github.com/lanhongsheng/operator-shape-derivation/blob/2619c00f74997b7d4b23ae86a77529ddc5ff0416/skills/ascend-op-workflow/references/tiling-knowledge/references/reduction/tiling-fields.md)。融合trait不得改变统计语义，资源与临时量必须入账。

## 融合足迹算例

合成例：R=1,024，x/residual/y 均 FP16、融合中间 FP32。一行的 x、residual、中间和 y 分别为 2,048/2,048/4,096/2,048 byte，单份同时存活就需 10,240 byte，尚未包含 gamma、统计与 scratch。按纯归约的一个标量输出估算会严重低估。

这不是强制保留全部项的分配方案：若选择合法复用或重算，可减少实际物理项；必须依据真实槽位与生命周期重新代入，不直接取逻辑阶段 max。
