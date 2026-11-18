# 逐元素：从字节预算到每核有效 tile

适用于同形状、连续且元素独立的分支。广播、stride、配对或归约未消除时不能直接 Flatten。以下是原 elewise 文档增强的参数/量纲部分，不重复基础 kernel 模板；平台对齐、可用核数和 API 支持读取目标版本。

## 物理预算

`U`、`reserve`、`alignment` 都用 byte；`T` 用元素；`e` 是该分支每元素 byte。对每个独立物理槽位单列大小，再求和：

```text
Σ_i align_up(bytes_i(T), alignment_i) + reserve ≤ U
```

`reserve` 不重复包含已列出的参数驻留或 scratch。单 dtype、等长物理 buffer 共 `c` 份且 `e` 整除对齐 `a` 时：

```text
tUpper = floor((U-reserve)/(c*e))
Tmax   = floor((U-reserve)/(c*a)) * (a/e)
```

`Tmax` 是满足该对齐组织的容量上界，不是最佳性能 tile。`Tmax≤0` 时本分支不可行。`U` 既然是字节，就不能在分子额外乘 8 后仍除以 byte/element。需要 bit 公式时，分子、分母必须同时换单位。

升精度包含 `c` 份输入/输出 dtype 槽位和 `K` 份独立 FP32 中间量时：

```text
c*align_up(T*e,a) + K*align_up(T*4,a) + reserve ≤ U
tUpper = floor((U-reserve)/(c*e+4*K))
```

从上界求满足实际对齐不等式的 T；占用单调时可二分。若实现要求 tile 本身按特定元素数对齐，求解后还要满足该条件。K 由实际 API、别名和生命周期决定，不从 dtype 名称猜测。

合成核算：`U=10000,reserve=0,c=2,e=2,K=1,a=32`。T=1250 时两份 half 各2528B、FP32一份5024B，总10080B超预算；T=1248 时为4992+4992=9984B，T=1249 又为10080B。合成数值只检验公式，不是硬件容量或切换阈值。

## 核间分配与核内循环分开

`N>0`，选择启动块数 P 后，一种连续分配示意为：

```text
block = align_up(ceil_div(N,P), blockAlignElements)
Q     = ceil_div(N,block)
validBlock(b) = min(block,N-b*block)       # 0≤b<Q
loops(b) = ceil_div(validBlock(b),T)
validTile(b,t) = min(T,validBlock(b)-t*T)  # 只访问有效 t
```

块对齐由字节换算到元素，不能固定“512元素”去代表各 dtype 的“512B”。核内循环的末 tile 按每核 `validBlock` 计算；全局可整除并不保证每个核无尾段。`N=0` 沿原规格的空 tensor 出口处理，不能用0作除数。

元素偏移和字节偏移分开：GM tensor 下标通常是元素，裸指针字节计算才乘 e；乘法、向上取整在足够宽且检查可表示的类型中完成，见[资源账本](resource-lifetime.md)。

## 选择而非填满

P、tile 大小、单双缓冲要联合考虑。深度翻倍增加物理占用，可能缩小 tile、增加循环；每核只有一轮时通常没有可重叠的下一轮。更小 tile 有时能增加独立任务，但单核分更多 tile 不自动增加核间并行。只按 UB 利用率接近100%选型会漏掉这些成本。

对混合 dtype、融合或 alias 变化重算物理占用；未覆盖运算的精度见[API 边界](api-precision.md)。沿原实现审查核参数如何进入 host/launch/kernel，不新增求解器接口或独立测试协议。
