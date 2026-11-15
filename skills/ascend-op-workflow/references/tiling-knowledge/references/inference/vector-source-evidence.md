# 十二个源码样本：观察与建议分列

据原 2026-09-29 调研，12 个去重样本，不是全仓普查或设备实测。下列 blob 链接与阅读边界来自该调研，制包未重新审计上游。公共入口 5/12（逐元素 2、广播 3），专用 7/12（行统计 5、语义配对 2）。调度 key、dtype 实例化数与算法数不能互换。

## Gelu

主类：逐元素公共模板。本轮路径：arch35。

按 dtype 实例化 GeluDAG，调用 ElewiseBaseTiling::DoTiling；本轮确认公共模板调用点，未读取该公共模板全部内部实现。

- [hicann/ops-nn/activation/gelu/op_host/arch35/gelu_tiling_arch35.cpp](https://github.com/hicann/ops-nn/blob/master/activation/gelu/op_host/arch35/gelu_tiling_arch35.cpp)
  - Blob SHA：`c0d4347a8f6b19807ef6895e2ff3abd87fce538f`；[不可变内容接口](https://api.github.com/repos/hicann/ops-nn/git/blobs/c0d4347a8f6b19807ef6895e2ff3abd87fce538f)。
  - 关键符号：`GeluTiling::RunTiling`, `TilingPrepareForGelu`。
  - 阅读范围：完整文件。

## AssignSub

主类：逐元素公共模板。本轮路径：arch35。

同 shape 校验后按 dtype 调用 ElewiseBaseTiling；借助 baseTiling.blockNum 设置核数。公共模板内部未展开审计。

- [hicann/ops-math/math/assign_sub/op_host/arch35/assign_sub_tiling_arch35.cpp](https://github.com/hicann/ops-math/blob/master/math/assign_sub/op_host/arch35/assign_sub_tiling_arch35.cpp)
  - Blob SHA：`e7b9487f89e63daea53b65e95438b9ee9dc4bee5`；[不可变内容接口](https://api.github.com/repos/hicann/ops-math/git/blobs/e7b9487f89e63daea53b65e95438b9ee9dc4bee5)。
  - 关键符号：`AssignSubTiling::RunTiling`, `CheckShape`, `SetTilingData`。
  - 阅读范围：完整文件。

## Add

主类：广播公共模板。本轮路径：arch35。

按混合 dtype、升精度、布尔等 DAG 分派，复用 BroadcastBaseTiling<OpDag>，GetSchMode 参与生成 tiling key；登记模板优先级。

- [hicann/ops-math/math/add/op_host/arch35/add_tiling_arch35.cpp](https://github.com/hicann/ops-math/blob/master/math/add/op_host/arch35/add_tiling_arch35.cpp)
  - Blob SHA：`892b40b3d1953f4e3d9e453c19cf30e93ee41436`；[不可变内容接口](https://api.github.com/repos/hicann/ops-math/git/blobs/892b40b3d1953f4e3d9e453c19cf30e93ee41436)。
  - 关键符号：`AddTiling::DoOpTiling`, `TilingForAdd`, `TilingPrepareForAdd`。
  - 阅读范围：完整文件。

## AxpyV2

主类：广播公共模板。本轮路径：arch35。

不同 dtype 的乘加 DAG 复用 BroadcastBaseTiling；公共模板调用点已确认，不据此推断其内部全部搬运分支。

- [hicann/ops-math/math/axpy_v2/op_host/arch35/axpy_v2_tiling_arch35.cpp](https://github.com/hicann/ops-math/blob/master/math/axpy_v2/op_host/arch35/axpy_v2_tiling_arch35.cpp)
  - Blob SHA：`71ce134a7385f4d2cca7f76b600ab34389720840`；[不可变内容接口](https://api.github.com/repos/hicann/ops-math/git/blobs/71ce134a7385f4d2cca7f76b600ab34389720840)。
  - 关键符号：`AxpyV2Tiling::DoOpTiling`, `TilingPrepareForAxpyV2`。
  - 阅读范围：源文件 1–230 行，覆盖完整文件。

## ClipByValue

主类：广播公共模板。本轮路径：arch35。

三个输入与输出的 dtype 校验后，调用 BroadcastBaseTiling<ClipByValueCompute<T>::OpDag>。

- [hicann/ops-math/conversion/clip_by_value/op_host/arch35/clip_by_value_tiling.cpp](https://github.com/hicann/ops-math/blob/master/conversion/clip_by_value/op_host/arch35/clip_by_value_tiling.cpp)
  - Blob SHA：`245798e17348fb48525b6ec587bbee91ebe94ef5`；[不可变内容接口](https://api.github.com/repos/hicann/ops-math/git/blobs/245798e17348fb48525b6ec587bbee91ebe94ef5)。
  - 关键符号：`ClipByValueTiling::DoOpTiling`, `TilingPrepareForClipByValue`。
  - 阅读范围：完整文件。

## RmsNorm

主类：按行统计与归约。本轮路径：经典 host；含 isSoc910B 等条件，不等同于 arch35 专用实现。

MergeN 为多行；不同缓冲占用决定 Normal / SingleRow / SplitD。kernel 的全局偏移按行分核，SplitD 在同核分段统计再分段输出，不是跨核拆一行。

- [hicann/ops-nn/norm/rms_norm/op_host/rms_norm_tiling.cpp](https://github.com/hicann/ops-nn/blob/master/norm/rms_norm/op_host/rms_norm_tiling.cpp)
  - Blob SHA：`e0245e4994f8dd8c01afc84db18084f001139853`；[不可变内容接口](https://api.github.com/repos/hicann/ops-nn/git/blobs/e0245e4994f8dd8c01afc84db18084f001139853)。
  - 关键符号：`CalMixDtypeTiling`。
  - 阅读范围：源文件 1–260 行，覆盖 MergeN / Normal / SingleRow / SplitD 入口及预算。
- [hicann/ops-nn/norm/rms_norm/op_kernel/rms_norm_split_d.h](https://github.com/hicann/ops-nn/blob/master/norm/rms_norm/op_kernel/rms_norm_split_d.h)
  - Blob SHA：`6a52092764011cf5a6a16ed2dbafa70463462bb6`；[不可变内容接口](https://api.github.com/repos/hicann/ops-nn/git/blobs/6a52092764011cf5a6a16ed2dbafa70463462bb6)。
  - 关键符号：`KernelRmsNormSplitD::Init`, `Process`, `SubProcess`。
  - 阅读范围：源文件 1–220 行。

## AddRmsNorm

主类：按行统计与归约。本轮路径：arch35 / RegBase。

先按 numRow 分核；从融合输入、输出、FP32 暂存和二分累加预算算 rowFactor；整行放不下时用 ubFactor / ubLoop 分段。

- [hicann/ops-nn/norm/add_rms_norm/op_host/add_rms_norm_tiling_arch35.cpp](https://github.com/hicann/ops-nn/blob/master/norm/add_rms_norm/op_host/add_rms_norm_tiling_arch35.cpp)
  - Blob SHA：`96d108c31f2985a457366bce2b9200159473c1fd`；[不可变内容接口](https://api.github.com/repos/hicann/ops-nn/git/blobs/96d108c31f2985a457366bce2b9200159473c1fd)。
  - 关键符号：`TilingAddRmsNormRegbase`, `ComputeTotalBufSize`。
  - 阅读范围：源文件 1–240 行。

## LayerNormV3

主类：按行统计与归约。本轮路径：arch35 / RegBase。

TwoPass 路径二分搜索可容纳完整 R 的行数 aFactor，并查询库 API scratch；Welford 路径以 tileLength 流式更新统计量，核间仍分独立行。LayerNorm 的同实现别名注册不另计样本。

- [hicann/ops-nn/norm/layer_norm_v3/op_host/arch35/layer_norm_v3_regbase_two_pass_tiling.cpp](https://github.com/hicann/ops-nn/blob/master/norm/layer_norm_v3/op_host/arch35/layer_norm_v3_regbase_two_pass_tiling.cpp)
  - Blob SHA：`e768130c60ac9d6059e7c66ab5fc438c6afa8a42`；[不可变内容接口](https://api.github.com/repos/hicann/ops-nn/git/blobs/e768130c60ac9d6059e7c66ab5fc438c6afa8a42)。
  - 关键符号：`CanFitInBuffer`, `IsCapable`, `DoLibApiTiling`。
  - 阅读范围：完整文件。
- [hicann/ops-nn/norm/layer_norm_v3/op_host/arch35/layer_norm_v3_welford_tiling.cpp](https://github.com/hicann/ops-nn/blob/master/norm/layer_norm_v3/op_host/arch35/layer_norm_v3_welford_tiling.cpp)
  - Blob SHA：`077621e6937ddf7ff8e7b943a7a6c80206a5c79f`；[不可变内容接口](https://api.github.com/repos/hicann/ops-nn/git/blobs/077621e6937ddf7ff8e7b943a7a6c80206a5c79f)。
  - 关键符号：`IsValidTileLength`, `DoLibApiTiling`, `DoOpTiling`。
  - 阅读范围：完整文件。

## SoftmaxV2

主类：按行统计与归约。本轮路径：arch35。

AR 全载按每行完整预算算可并行处理的行数；AR Recompute 在同核切 R；ARA 全载保留完整 R、切连续 A0，并联合 UB 与核数确定 tileA0Len。三个路径仍只计一个算子。

- [hicann/ops-nn/activation/softmax_v2/op_host/arch35/softmax_v2_ar_full_load_tiling.cpp](https://github.com/hicann/ops-nn/blob/master/activation/softmax_v2/op_host/arch35/softmax_v2_ar_full_load_tiling.cpp)
  - Blob SHA：`d95d6d98a14f9481a665852976875329fba9fc5b`；[不可变内容接口](https://api.github.com/repos/hicann/ops-nn/git/blobs/d95d6d98a14f9481a665852976875329fba9fc5b)。
  - 关键符号：`SoftmaxV2TilingAR::DoOpTiling`, `IsCapable`。
  - 阅读范围：完整文件。
- [hicann/ops-nn/activation/softmax_v2/op_host/arch35/softmax_v2_ar_recompute_tiling.cpp](https://github.com/hicann/ops-nn/blob/master/activation/softmax_v2/op_host/arch35/softmax_v2_ar_recompute_tiling.cpp)
  - Blob SHA：`438ba96f3fd64a8d436b480dffce597962f5f308`；[不可变内容接口](https://api.github.com/repos/hicann/ops-nn/git/blobs/438ba96f3fd64a8d436b480dffce597962f5f308)。
  - 关键符号：`SoftmaxV2TilingARRecompute::DoOpTiling`, `BinarySummationTiling`。
  - 阅读范围：完整文件。
- [hicann/ops-nn/activation/softmax_v2/op_host/arch35/softmax_v2_ara_full_load_tiling.cpp](https://github.com/hicann/ops-nn/blob/master/activation/softmax_v2/op_host/arch35/softmax_v2_ara_full_load_tiling.cpp)
  - Blob SHA：`e4ef9ab6c65cd2635b0cbbce123b5bbc29f4643b`；[不可变内容接口](https://api.github.com/repos/hicann/ops-nn/git/blobs/e4ef9ab6c65cd2635b0cbbce123b5bbc29f4643b)。
  - 关键符号：`SoftmaxV2ARATiling::DoOpTiling`, `BinaryAddTiling`。
  - 阅读范围：完整文件。

## DynamicQuant

主类：按行统计与归约。本轮路径：经典 host；有独立 310P / arch35 路由，未将其所有分支混合审计。

按 smooth、group、dtype、单/双缓冲计算每行占用；支持多行、长行核内分段，以及额外行的大小核分配。特化 shape 条件不是通用阈值。

- [hicann/ops-nn/quant/dynamic_quant/op_host/dynamic_quant_tiling.cpp](https://github.com/hicann/ops-nn/blob/master/quant/dynamic_quant/op_host/dynamic_quant_tiling.cpp)
  - Blob SHA：`87a7f483a8637324b8a94c1405eb7b7cdb84c55f`；[不可变内容接口](https://api.github.com/repos/hicann/ops-nn/git/blobs/87a7f483a8637324b8a94c1405eb7b7cdb84c55f)。
  - 关键符号：`SetTilingData`, `CalculateMaxUbSizePerRow`, `CheckMultiRowPreconditions`, `CalculateMultiRowCoreDistribution`。
  - 阅读范围：源文件 1–300、410–760 行；第二段输出在末尾截断，核心所列函数已读取。

## SwiGlu

主类：语义配对 / 二维专用模板。本轮路径：公共多平台 host；显式包含 DAV_2002 等限制。

搜索 baseRowLen × baseColLen，结合搬运 stride / blockCount 限制；排序目标先保核数再减 tile 数。双缓冲每核 2 tile 时试单缓冲，只有变成 1 tile 且核数不减少才切换。

- [hicann/ops-nn/activation/swi_glu/op_host/swi_glu_tiling.cpp](https://github.com/hicann/ops-nn/blob/master/activation/swi_glu/op_host/swi_glu_tiling.cpp)
  - Blob SHA：`b495e91ea3669e67205a49d36eb33b797570ffc6`；[不可变内容接口](https://api.github.com/repos/hicann/ops-nn/git/blobs/b495e91ea3669e67205a49d36eb33b797570ffc6)。
  - 关键符号：`SetTotalShape`, `GetBufferNumAndDataLenPerUB`, `SaveOptBaseShape`, `CalcOptBaseShape`, `CalcTiling`。
  - 阅读范围：文件开头至 SaveOptBaseShape 的可见部分；另读取源文件 300–560 行。

## RotaryPositionEmbedding

主类：语义配对 / 二维专用模板。本轮路径：RegBase，所选 AB 路径要求 layout == RopeLayout::SBND。

按 BS 分核；BS 较小时再分 N 以增加独立任务。UB 内联合决定 ubFactorBS / ubFactorN，并保留 dSplitCoef、rotaryMode 语义。没有把其他 RoPE 分支一并宣称已审计。

- [hicann/ops-transformer/posembedding/rotary_position_embedding/op_host/rope_regbase_tiling_ab.cpp](https://github.com/hicann/ops-transformer/blob/master/posembedding/rotary_position_embedding/op_host/rope_regbase_tiling_ab.cpp)
  - Blob SHA：`625a7ac8be2ed68ed40b0a27719729536183897a`；[不可变内容接口](https://api.github.com/repos/hicann/ops-transformer/git/blobs/625a7ac8be2ed68ed40b0a27719729536183897a)。
  - 关键符号：`RopeRegBaseTilingClassAB::DoOpTiling`, `IsCapable`, `PostTiling`。
  - 阅读范围：完整文件。

## 如何使用这些证据

同一算子可以命中多行；未记录不等于不支持。公共模板内部没有展开，所以“显式 UB 预算 7/12”不能解释为另外 5 个算子没有 UB 预算。

| 机制 | 本轮记录数 | 样本 |
|---|---:|---|
| 复用 ElewiseBaseTiling | 2/12 | Gelu、AssignSub |
| 复用 BroadcastBaseTiling | 3/12 | Add、AxpyV2、ClipByValue |
| 专用路径中显式核算 UB | 7/12 | RmsNorm、AddRmsNorm、LayerNormV3、SoftmaxV2、DynamicQuant、SwiGlu、RotaryPositionEmbedding |
| 专用路径中显式划分核间任务 | 7/12 | RmsNorm、AddRmsNorm、LayerNormV3、SoftmaxV2、DynamicQuant、SwiGlu、RotaryPositionEmbedding |
| 专用路径中显式对齐或尾处理 | 7/12 | RmsNorm、AddRmsNorm、LayerNormV3、SoftmaxV2、DynamicQuant、SwiGlu、RotaryPositionEmbedding |
| 完整 R 工作集驻留 UB 的路径 | 5/12 | RmsNorm、AddRmsNorm、LayerNormV3、SoftmaxV2、DynamicQuant |
| 多行处理 / Merge-row 能力 | 5/12 | RmsNorm、AddRmsNorm、LayerNormV3、SoftmaxV2、DynamicQuant |
| 同核分段 R / 流式统计 | 5/12 | RmsNorm、AddRmsNorm、LayerNormV3、SoftmaxV2、DynamicQuant |
| ARA 非尾轴归约路径 | 1/12 | SoftmaxV2 |
| 专用广播/配对二维划分 | 2/12 | SwiGlu、RotaryPositionEmbedding |
| 根据 workload 选择单/双缓冲 | 2/12 | DynamicQuant、SwiGlu |
| 直接可见模板优先级注册 | 6/12 | Add、AxpyV2、ClipByValue、LayerNormV3、SoftmaxV2、RotaryPositionEmbedding |
| 直接调用库 API 查询统计/归约暂存 | 1/12 | LayerNormV3 |

### 4.3 不应混淆的概念

- 核内 Split-R 不增加独立行的核间并行度；跨核 Split-R 需要另建 partial、合并与同步设计。
- 双缓冲、NDDMA、Welford 分别属于流水、搬运、数值统计维度，不宜与基础切分互斥分类。
- `L2_CACHE_LINE_SIZE` 常量只证明对齐/搬运粒度的考虑，不证明实现了 L2 外层复用分块。
- `TilingKey` 可以编码 dtype 或调度模式；不能简单用 key 数量统计算法模板数量。
- 本轮没有生产代码正证据覆盖跨核 Split-R、L2 外层复用、长度分桶和 Sort/TopK/Scatter；不把它们记为“CANN 没有”。

### 5.1 资源账本：把完整生命周期算进去

作为设计建议，统一用 byte 计算各物理 buffer 的分配，区分输入/输出 dtype、FP32 中间量、队列份数、参数常驻、库 API scratch 与对齐。对可合法复用的生命周期使用同一物理槽位。LayerNorm 的 GetLayerNormMaxMinTmpSize / GetWelford*MaxMinTmpSize 提供了查询 API 暂存的具体样本。

### 5.2 tile 和核数联合选择，不只追求 UB 满载

SwiGlu 的候选评分优先保留更多工作核，再比较 tile 数、tile 面积和完整 tile 数。AR full-load 的批行数需受每核行数约束；RoPE 在 BS 任务少时沿 N 增加独立任务，而不是破坏 D 维配对语义。

### 5.3 双缓冲应是选择题

SwiGlu 的具体判定是：双缓冲每核恰有 2 个 tile 时，试算单缓冲；若单缓冲变成 1 个 tile 且使用核数不减少，才关闭双缓冲。DynamicQuant 也根据每行完整 UB 用量以及 group 条件选择路径。两者均不是“永远双缓冲”的实现。

### 5.4 公共框架与专用模板并存

本样本 5/12 个算子直接复用公共 Elewise/Broadcast tiling，7/12 个具有专用资源与切分计算。因此后续不宜只沉淀手写公式；还应沉淀何时表达 OpDag 并复用公共 tiling、何时采用自定义多行/分段/配对模板。公共框架的全部内部能力与交付环境版本仍需单独核验。

设计方法、可复制工程骨架和参数求解工具是三个层次；逐元素求解示例不能证明通用归约也受支持。旧 Elewise 文档的 bit/byte 示例是文档量纲风险，非生产 kernel 错误结论。
