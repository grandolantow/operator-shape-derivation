# Pooling 类算子场景路由（MaxPool / AvgPool）

> **状态**：3.0.0-experimental 新增的**假设性路由卡**：候选切分是合法性与成本比较的起点，
> 不是实测排序；本文不含任何平台查询值或实测结论。
> 文中平台常数（对齐字节数等）为示例，需平台查询回填。

---

## 一、语义归一化

设计前先把以下语义项固定下来（它们决定合法性，tiling 不能改变它们）：

| 语义项 | 说明 |
|--------|------|
| kernel / stride / pad / dilation / ceil_mode | 从算子原始规格确定窗口、步进、填充、dilation、输出取整及边界修正。仅在 dilation=1、ceil_mode=false、每维对称 pad 且规格无其他尺寸修正时，示例公式为 `O = floor_div(D + 2p − k, s) + 1`；合法尺寸由原始规格和 host 校验决定 |
| channel 布局 | 标准紧凑行主序下 NCHW 的 W 连续、NHWC 的 C 连续。实际存在非标准 stride、分块或其他格式时，以原始规格的真实地址映射为准 |
| padding 值语义 | MaxPool：pad 区域不参与 max（等价 −inf 语义）或按实现定义，需显式确认；AvgPool：`count_include_pad` 决定分母是否含 pad 计数 |
| 窗口 ↔ 输出对应 | 池化窗口必须与输出索引**一一对应**：按输出索引驱动迭代（每个输出位置恰好取一个窗口），保证不重不漏；不要按输入索引扫描 |

对上述标准紧凑布局，元素偏移分别为
`NCHW: ((n*C + c)*H + h)*W + w` 和 `NHWC: ((n*H + h)*W + w)*C + c`。
因此 NCHW 中 W 步长为 1、C 步长为 `H*W`；NHWC 中 C 步长为 1、W 步长为 `C`。

---

## 二、候选切分（layout-aware，连续维优先）

| 候选 | 切分方法 | 适用特征 | 备注 |
|------|---------|---------|------|
| **(a) 按输出行/平面分核** | 每核负责若干输出行（或输出平面）；同一输出行内窗口沿 W 滑动 | 通用起点；`stride < kernel` 时输入行可复用（重叠窗口共享读） | 复用要求"一行载入、UB 内多窗口使用"，见第三节读放大 |
| **(b) 按 C 块分核** | 通道块独立分核，无跨通道依赖 | NHWC 中同一空间位置的 C 连续；NCHW 也可独立分配 C 平面，但不能假设跨 C 窗口数据连续 | C 块大小决定窗口块字节数；按真实 stride 计算搬运 |
| **(c) 二维 tile（OH×OW 或 C×OW）** | 单一维度任务数不足时，把两个独立维度组合成 tile | 输出平面小、核间任务不够时比较；搬运连续性取决于布局、tile 和实际 stride | tile 的两个维度都必须满足各自语义独立性 |
| **(d) 窗口整体驻留 UB 的 FullLoad（小特征图）** | 整个（或按 C 块的）输入窗口块 + 输出块驻留 UB，核内循环完成 | 小特征图 / 小 C 块，账本放得下 | 账本见第三节；放不下则沿 W（或 OW）分段核内循环 |

- 候选 (a)–(d) 可叠加（如 按输出行分核 + C 块 + 核内 W 循环）。
- 选择是**合法性（账本放得下、映射不越界）+ 成本（workload 比较）**两个问题；
  无"必须多 kernel"、无"必须用满核"的要求。

---

## 三、UB 账本骨架（符号化）

```text
winCopies*win_b + outCopies*out_b + tmp_b + reserveBytes ≤ ubSize

win_b = 每个输入槽的窗口数据实际分配字节数，按实际布局、分块及缓冲逐项对齐
out_b = 对齐后的输出块字节数
tmp_b = 临时/比较中间（MaxPool 的比较链、AvgPool 的累加，含升精度 fp32 中间）
winCopies / outCopies = 各自 queue 的物理槽位深度 × 每槽份数
```

若 `kH*kW*C_tile` 个输入元素被打包到单个连续 UB 槽且只需该槽一次整体对齐，
可按 `align_up(kH*kW*C_tile*elemBytes, alignBytes)` 估算该槽；这不表示原 GM 窗口整体连续。
若逐行或逐片分别分配、对齐，应逐项求和；NHWC 的 C 内层连续，NCHW 的 W 内层连续。

对齐与 copies 的口径、队列槽位生命周期见 [../common/resource-lifetime.md](../common/resource-lifetime.md)；
逐 buffer 对齐与混合 dtype 计字节方法见 [../elewise/tiling.md](../elewise/tiling.md)。

**GM 读放大（成本项，不是合法性项）**：`stride < kernel` 时同一输入元素被多个窗口读取。
单个空间维的重叠因子上界为 `ceil_div(k, s)`（例：合成值 `W = 8, k = 3, s = 1, p = 1`
→ `W_out = floor_div(8 + 2 - 3, 1) + 1 = 8` 个输出，每个输入位置至多被 `ceil_div(3,1) = 3`
个窗口覆盖；逐窗口搬运的 GM 读上界约为一次载入的 3 倍）。
组织为"一次载入输入行、UB 内供多窗口复用"可把读次数压回输入规模量级；
两种写法（一行载入多窗口复用 vs 按窗口重复载入）是**成本项**，按 workload 比较。

---

## 四、边界条件

| 边界 | 要点 |
|------|------|
| W/H 不整除 stride/tile | 输出尺寸按原始规格的属性和取整规则计算；尾窗口按输出索引驱动，不得越窗读取 |
| pad 区域 | 只参与**按语义定义**的计算：MaxPool 的 pad 不入 max；AvgPool 分母是否含 pad 由 `count_include_pad` 决定；pad 值不得进入非法比较（如以 0 填充参与 max 会错） |
| 输出索引越界守卫 | 尾核/尾块的输出行数按有效数迭代（口径同 [../common/resource-lifetime.md](../common/resource-lifetime.md) 第五节） |
| N=1 / C=1 | 并行维度退化：只剩空间维或 C 维提供任务；任务数不足属并行度问题，不得为凑核数破坏窗口语义 |
| 极端 kernel | 窗口与尺寸是否合法按原始规格及 host 校验；超大窗口使窗口块超账本 → 沿 W/OW 分段核内循环（候选 (d) 的失败出口） |

---

## 五、与其他类别的关系

- 池化没有跨行归约语义（窗口内归约、窗口间独立），账本与守卫口径与
  Reduction 的行归约不同，不要套用 [../reduction/patterns.md](../reduction/patterns.md) 的 AR 路由。
- 小特征图全载（候选 d）失败后的核内分段，形态上接近 EleWise 的 UB 切分 +
  窗口边界守卫，可参考 [../elewise/tiling.md](../elewise/tiling.md) 的公式风格。
