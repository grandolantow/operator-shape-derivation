# Vector 选型的源码观察边界

以下转述用户提供的2026-09-29调研；不是本次重新联网审计、全仓统计或硬件实测。原调研固定 CANNBot `80bd6c22c85f830774369fc52ab447424921e8f3`，源码来自 hicann 的公开镜像；这些镜像身份不能代替目标平台当前官方资料。blob 链接固定观察对象，读取范围按原记录保留。

| 样本 | 原调研观察 | 固定内容与阅读范围 |
|---|---|---|
| Gelu | 主类：逐元素公共模板。本轮路径：arch35。 按 dtype 实例化 GeluDAG，调用 ElewiseBaseTiling::DoTiling；本轮确认公共模板调用点，未读取该公共模板全部内部实现。 | [blob 1](https://api.github.com/repos/hicann/ops-nn/git/blobs/c0d4347a8f6b19807ef6895e2ff3abd87fce538f)；范围：完整文件。 |
| AssignSub | 主类：逐元素公共模板。本轮路径：arch35。 同 shape 校验后按 dtype 调用 ElewiseBaseTiling；借助 baseTiling.blockNum 设置核数。公共模板内部未展开审计。 | [blob 1](https://api.github.com/repos/hicann/ops-math/git/blobs/e7b9487f89e63daea53b65e95438b9ee9dc4bee5)；范围：完整文件。 |
| Add | 主类：广播公共模板。本轮路径：arch35。 按混合 dtype、升精度、布尔等 DAG 分派，复用 BroadcastBaseTiling<OpDag>，GetSchMode 参与生成 tiling key；登记模板优先级。 | [blob 1](https://api.github.com/repos/hicann/ops-math/git/blobs/892b40b3d1953f4e3d9e453c19cf30e93ee41436)；范围：完整文件。 |
| AxpyV2 | 主类：广播公共模板。本轮路径：arch35。 不同 dtype 的乘加 DAG 复用 BroadcastBaseTiling；公共模板调用点已确认，不据此推断其内部全部搬运分支。 | [blob 1](https://api.github.com/repos/hicann/ops-math/git/blobs/71ce134a7385f4d2cca7f76b600ab34389720840)；范围：源文件 1–230 行，覆盖完整文件。 |
| ClipByValue | 主类：广播公共模板。本轮路径：arch35。 三个输入与输出的 dtype 校验后，调用 BroadcastBaseTiling<ClipByValueCompute<T>::OpDag>。 | [blob 1](https://api.github.com/repos/hicann/ops-math/git/blobs/245798e17348fb48525b6ec587bbee91ebe94ef5)；范围：完整文件。 |
| RmsNorm | 主类：按行统计与归约。本轮路径：经典 host；含 isSoc910B 等条件，不等同于 arch35 专用实现。 MergeN 为多行；不同缓冲占用决定 Normal / SingleRow / SplitD。kernel 的全局偏移按行分核，SplitD 在同核分段统计再分段输出，不是跨核拆一行。 | [blob 1](https://api.github.com/repos/hicann/ops-nn/git/blobs/e0245e4994f8dd8c01afc84db18084f001139853)；[blob 2](https://api.github.com/repos/hicann/ops-nn/git/blobs/6a52092764011cf5a6a16ed2dbafa70463462bb6)；范围：源文件 1–260 行，覆盖 MergeN / Normal / SingleRow / SplitD 入口及预算。 / 源文件 1–220 行。 |
| AddRmsNorm | 主类：按行统计与归约。本轮路径：arch35 / RegBase。 先按 numRow 分核；从融合输入、输出、FP32 暂存和二分累加预算算 rowFactor；整行放不下时用 ubFactor / ubLoop 分段。 | [blob 1](https://api.github.com/repos/hicann/ops-nn/git/blobs/96d108c31f2985a457366bce2b9200159473c1fd)；范围：源文件 1–240 行。 |
| LayerNormV3 | 主类：按行统计与归约。本轮路径：arch35 / RegBase。 TwoPass 路径二分搜索可容纳完整 R 的行数 aFactor，并查询库 API scratch；Welford 路径以 tileLength 流式更新统计量，核间仍分独立行。LayerNorm 的同实现别名注册不另计样本。 | [blob 1](https://api.github.com/repos/hicann/ops-nn/git/blobs/e768130c60ac9d6059e7c66ab5fc438c6afa8a42)；[blob 2](https://api.github.com/repos/hicann/ops-nn/git/blobs/077621e6937ddf7ff8e7b943a7a6c80206a5c79f)；范围：完整文件。 / 完整文件。 |
| SoftmaxV2 | 主类：按行统计与归约。本轮路径：arch35。 AR 全载按每行完整预算算可并行处理的行数；AR Recompute 在同核切 R；ARA 全载保留完整 R、切连续 A0，并联合 UB 与核数确定 tileA0Len。三个路径仍只计一个算子。 | [blob 1](https://api.github.com/repos/hicann/ops-nn/git/blobs/d95d6d98a14f9481a665852976875329fba9fc5b)；[blob 2](https://api.github.com/repos/hicann/ops-nn/git/blobs/438ba96f3fd64a8d436b480dffce597962f5f308)；[blob 3](https://api.github.com/repos/hicann/ops-nn/git/blobs/e4ef9ab6c65cd2635b0cbbce123b5bbc29f4643b)；范围：完整文件。 / 完整文件。 / 完整文件。 |
| DynamicQuant | 主类：按行统计与归约。本轮路径：经典 host；有独立 310P / arch35 路由，未将其所有分支混合审计。 按 smooth、group、dtype、单/双缓冲计算每行占用；支持多行、长行核内分段，以及额外行的大小核分配。特化 shape 条件不是通用阈值。 | [blob 1](https://api.github.com/repos/hicann/ops-nn/git/blobs/87a7f483a8637324b8a94c1405eb7b7cdb84c55f)；范围：源文件 1–300、410–760 行；第二段输出在末尾截断，核心所列函数已读取。 |
| SwiGlu | 主类：语义配对 / 二维专用模板。本轮路径：公共多平台 host；显式包含 DAV_2002 等限制。 搜索 baseRowLen × baseColLen，结合搬运 stride / blockCount 限制；排序目标先保核数再减 tile 数。双缓冲每核 2 tile 时试单缓冲，只有变成 1 tile 且核数不减少才切换。 | [blob 1](https://api.github.com/repos/hicann/ops-nn/git/blobs/b495e91ea3669e67205a49d36eb33b797570ffc6)；范围：文件开头至 SaveOptBaseShape 的可见部分；另读取源文件 300–560 行。 |
| RotaryPositionEmbedding | 主类：语义配对 / 二维专用模板。本轮路径：RegBase，所选 AB 路径要求 layout == RopeLayout::SBND。 按 BS 分核；BS 较小时再分 N 以增加独立任务。UB 内联合决定 ubFactorBS / ubFactorN，并保留 dSplitCoef、rotaryMode 语义。没有把其他 RoPE 分支一并宣称已审计。 | [blob 1](https://api.github.com/repos/hicann/ops-transformer/git/blobs/625a7ac8be2ed68ed40b0a27719729536183897a)；范围：完整文件。 |

## 从样本提炼的选择依据

- 逐元素/广播可表达 OpDag 并复用公共 tiling，但只读到调用入口不等于已核公共模板的全部支持域。是否采用仍先查当前安装版本。
- 专用行统计需要把多行、整行驻留、核内分段、FP32 中间和 API scratch 一起算；同一算子有多个路径不等于多个独立样本。
- tile与核数联合选择：SwiGlu样本先保工作核数再比较tile数量；RoPE样本利用其他语义独立轴，不是任意拆旋转维。
- 单双缓冲是成本选择。样本的“2 tile改1 tile且核数不减”是特定实现条件，不是所有算子的规则。
- `TilingKey` 可编码dtype或调度模式，不能用key数量统计算法数；cache-line对齐常量不能证明已有L2外层复用。
- 未观察到某机制不能写成平台不支持，源码观察不能替代本任务精度和性能测量。
