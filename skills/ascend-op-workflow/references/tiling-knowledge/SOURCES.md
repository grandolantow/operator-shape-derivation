# Tiling 知识的来源与维护

本目录保留工作流独有及增强知识的正文、公式、反例和选型案例；仅已确认重复的基础知识从 CANNBot 引用。策略优先级统一见[生成设计评审](../generation-design-review.md#知识来源与策略优先级)，阅读入口见 [INDEX.md](INDEX.md)。

## 引用约定

- 本库正文与本地 Markdown 链接由本仓维护。标为 CANNBot 的 `references/...` 是相对任务 checkout 中 `ops/ascendc-tiling-design/` 的路径提示；先从该技能的 `SKILL.md` / 索引定位同主题资料。
- checkout 沿用[执行适配](../cannbot-execution.md#路径与安装)中的 `cannbot_root` / `CANNBOT_SOURCE_ROOT`，不另设知识库地址、镜像或分支。目录变化时按该 checkout 的实际索引与符号查找；找不到则记录缺口，不能自动切换到历史 fork。
- 下方提交、blob 与哈希只说明当时核对或观察的内容，不是当前任务必须使用的版本。任务仍按既有合同/manifest 记录实际来源与版本；变更适用域时复核相关知识，本工作流策略优先级沿用生成设计评审。

## 历史来源与核对范围

- 原材料：[PR #6](https://github.com/grandolantow/operator-shape-derivation/pull/6)，固定提交 [2619c00](https://github.com/lanhongsheng/operator-shape-derivation/tree/2619c00f74997b7d4b23ae86a77529ddc5ff0416)，其[来源清单](https://github.com/lanhongsheng/operator-shape-derivation/blob/2619c00f74997b7d4b23ae86a77529ddc5ff0416/docs/SHAPE_TILING_SOURCES.json)声明为 CANNBot 基础资料及 experimental_REV5（2026-11-05）增强快照。
- 实际对照：CANNBot [bcb8067](https://gitcode.com/chenshushu2020/cannbot-skills/tree/bcb8067bd6ebab19e490b317ad8250e25a18316b) 的 `ops/ascendc-tiling-design/`，核对时该目录无未提交修改。下表哈希是此提交的实际文件字节，不把原清单标签当重复证明。
- 逐一核对原目录 **55 份 Markdown**：32 份正文重复（28 份字节相同、3 份仅文末空行、1 份仅行尾空白）；其余 9 份有内容/导航差异、14 份在对照目录没有同路径文件，按下表保留或归并，不因缺少同路径就推定其他位置没有相关知识。
- 此次对照版本用于证明下面的去重判断，不是依赖版本要求。现场内容变化不自动推翻本地增强，先核差异与适用域；不把路径或来源记录当已读或已覆盖的证明。

下表“原路径”相对原快照的 `skills/ascend-op-workflow/references/tiling-knowledge/`；原快照身份只在上面记录一次。所有本地正文由本仓维护，交付字节以本仓提交与安装 manifest 为准。

## 本地保留正文

| 原路径 | 当前正文 | 主要保留内容 |
|---|---|---|
| `references/common/shape-selection.md` | [common/shape-selection.md](common/shape-selection.md) | 语义归一化、六类候选、条件策略、任务/核数/波次、参数化覆盖。 |
| `references/common/resource-lifetime.md` | [common/resource-lifetime.md](common/resource-lifetime.md) | 物理槽位与复用、队列份数、容量取证、溢出/尾块/DMA 位宽反例。 |
| `references/common/runtime-cost.md` | [common/runtime-cost.md](common/runtime-cost.md) | Host 准备、发布、分配、缓存及冷启动/eager/图模式成本。 |
| `references/common/operator-patterns.md` | [common/operator-patterns.md](common/operator-patterns.md) | 广播、重排、门控/旋转配对、完整统计后量化，以及邻域/分桶/冲突更新。 |
| `references/common/api-precision-notes.md` | [common/api-precision-notes.md](common/api-precision-notes.md) | Cast 重载反例、NR 误差式、别名、dtype 证据与比较器短路；实验记录未恢复。 |
| `references/elewise/patterns.md` | [elewise/patterns.md](elewise/patterns.md) | 原快照仅新增精度路由缺口限定，其他段落与 CANNBot 重叠。本次保留整篇路由并修正连续性、中间舍入合同、字节对齐和经验目标粒度，避免外引旧路由与本地公式冲突；不将重复段落计作独有算法。 |
| `references/elewise/tiling.md` | [elewise/tiling.md](elewise/tiling.md) | bytes/bits、dtype 对齐、物理预算定义式、完整求解示例与混合 dtype 案例。 |
| `references/reduction/ar-colsplit.md` | [reduction/ar-colsplit.md](reduction/ar-colsplit.md) | chunkCols 公式、统计驻留、核内分段与重读/重算成本。 |
| `references/reduction/ar-fullload.md` | [reduction/ar-fullload.md](reduction/ar-fullload.md) | 全工作集 R_max、scratch/输出槽位、有效 count 与单行数据流。 |
| `references/reduction/ar-merge-row.md` | [reduction/ar-merge-row.md](reduction/ar-merge-row.md) | B_M_max、两种任务组织、各自尾组公式和合成算例。 |
| `references/reduction/norm-fusion.md` | [reduction/norm-fusion.md](reduction/norm-fusion.md) | 完整统计、保留/重读/重算、融合资源、scale/epsilon/分组边界。 |
| `references/reduction/patterns.md` | [reduction/patterns.md](reduction/patterns.md) | 全工作集可行性、Merge-row、核内/跨核区别及融合路由。 |
| `references/pooling/patterns.md` | [pooling/patterns.md](pooling/patterns.md) | 窗口语义、布局地址式、候选切分、物理预算和读放大算例。 |
| `references/inference/vector-recipes.md` | [inference/vector-recipes.md](inference/vector-recipes.md) | 六类切分、五类条件策略与 shape 演练起点。 |
| `references/inference/inference-routes.md` | [inference/inference-routes.md](inference/inference-routes.md) | 十类推理场景及配对/量化/索引/扫描语义。 |
| `references/inference/add-rmsnorm-keys.md` | [inference/add-rmsnorm-keys.md](inference/add-rmsnorm-keys.md) | 不同架构的 key 与参数、重读/重算差异和实现条件。 |
| `references/inference/vector-source-evidence.md` | [inference/vector-source-evidence.md](inference/vector-source-evidence.md) | 十二样本的源码机制、固定 blob、符号、阅读范围及证据边界。 |

## 混合正文与入口归并

以下三份专项文档与对照 CANNBot 逐段比较，除所列 API 限定增量外正文相同。增量保留在本地，基础算法外引；不能直接采用外部未限定的说法。

| 原路径及重复正文 | 本地增量或去向 |
|---|---|
| `references/sort/patterns.md` | [API 精度注记](common/api-precision-notes.md#3-in-place--别名能力逐重载核对)：同 dtype 省略 Cast 的条件；[归并边界](sort/merge-boundaries.md)先于基础方案。 |
| `references/sort/alg-two-level-mrgsort.md` | Cast 独立输出是保守选择，非 API 定律；上述两卡保留增量，并澄清有效长度、workspace 与屏障参与边界。 |
| `references/reduction/with-index.md` | [编译器能力与索引表示](common/api-precision-notes.md#5-编译器能力与索引表示)：static_cast 的版本边界。 |
| `INDEX.md` | 类别知识路由保留于 [INDEX.md](INDEX.md)，重复工作流步骤由既有生成设计评审维护。 |
| `reading-routes.md` | 合并入同一 INDEX，不保留第二套读取/执行流程。 |
| `knowledge-coverage.md` | 四份输入的身份与去向并入下面的来源表，移除“上一版/现在”的发布叙事。 |

原 `shape-tiling.md` 的设计/交接步骤合入既有[生成设计评审](../generation-design-review.md)，机制例子纳入资源与算子模式正文；不恢复独立 handoff 模板。参数映射继续在原 DESIGN 中记录。

## 已确认重复的基础资料

下列 32 项仅外引，按引用约定从当前任务的 CANNBot checkout 定位。路径相对 `ops/ascendc-tiling-design/`；哈希是历史核对文件的 SHA-256，不要求当前文件与此哈希相同。“文末空行/行尾空白”不包含语义或导航变更。

| 原路径 / CANNBot 定位路径 | 当时比较结果 | 历史对照 SHA-256 |
|---|---|---|
| `references/broadcast/dynamic-ub-broadcast.md` | 字节相同 | `8d0fe5304c1399385b3faaf1964f22717f9ee236f1912ecf130f62907d5f2abc` |
| `references/broadcast/nddma-broadcast.md` | 字节相同 | `b7a1aca510fde5d007325f3df3842901fb5f6a0d68fb823633a4f6f4b5344c75` |
| `references/broadcast/onedim.md` | 字节相同 | `9b06639c66acdd912d39289720aa2ec668c9f4d1df7f423c9f601c2ce63a5738` |
| `references/broadcast/patterns.md` | 字节相同 | `a5da6eee04624b005022cc13135f23c900c6adda91938e0e53464b9d13e928ca` |
| `references/broadcast/ub-broadcast.md` | 字节相同 | `4aa3bffcf13401bfa2e2f2d13525a23bb107cf7ebf50f900db54bb08dccaa6ab` |
| `references/conversion/patterns.md` | 仅文末空行 | `3b11c42fec83631ee8b2c26eefd3ac7b16b2606b6a09ea7ad15991c0b806e306` |
| `references/flashattention/design/_governance.md` | 字节相同 | `ad1bddc0e6ef72d8130f71dac3fa8dbf250755c88ea84b1aedd4428edabf1959` |
| `references/flashattention/design/execution.md` | 字节相同 | `2c13d95ec96cb1106694cdfc976f3dfb9d57a5b5de432251206fad1ed377ada0` |
| `references/flashattention/design/resources.md` | 字节相同 | `36c29cd0eb871d5357a461228ea4e7431caf25f889fb3ae5c1ac7753fcfe5f0e` |
| `references/flashattention/design/shape.md` | 字节相同 | `d7aba4c9f89b0422b630646f922fbe4705ff5329645e7f3bc85829a3b4c23a0b` |
| `references/flashattention/foundation/composition.md` | 字节相同 | `d23c46ad2d8e731b24c22826c574de8e529d34a27d8391a9cbdbc59633379923` |
| `references/flashattention/foundation/extension_points.md` | 字节相同 | `389fbd88a946c032bc578003b2e2334246f6e49e912dd150260092f36763984e` |
| `references/flashattention/foundation/fundamentals.md` | 字节相同 | `97841e1a8de2f7e0d1c7471729c47660cf6dd23f5d64e1f384507b4ad3322020` |
| `references/flashattention/foundation/roofline.md` | 字节相同 | `1925bae9289b83b0cb193e9d3c5229535b6d72dc3dea9d23d9b9ac641f70f499` |
| `references/flashattention/implementation_ref.md` | 字节相同 | `c950dec94c4148d46e1967057461a105819d233958daa5b7e693bf9cdccbe2f4` |
| `references/flashattention/patterns.md` | 字节相同 | `2dd2a9c6d500a6aed50b4d8b54f9e40cb3f2a802660142e075842d08270d98b6` |
| `references/flashattention/specialization/feature_flags.md` | 字节相同 | `460d0b301f587f7f244faa8adbe16907ba4ebf83779051679c39eb206a0bf040` |
| `references/flashattention/specialization/sparse_design.md` | 字节相同 | `a8e6d32e88dc421896645eda7050f56bc1ba80c5dffb597326c1a6977d474711` |
| `references/flashattention/subfamilies/base_design.md` | 字节相同 | `e908ea3ee3bcdb0142b96158554140f5552c255614cef58283bb31a752c360c6` |
| `references/flashattention/subfamilies/quantization_design.md` | 字节相同 | `804828aa03e475264bb3a6a1d57b94930d4f5f5b2d7a04775d01777c43f81e5b` |
| `references/matmul/ascendc-api-gmm-tiling.md` | 字节相同 | `90d9b2c693a9fb876326157a618e383413c28cf660e8d4f92941a96b6c593cb1` |
| `references/matmul/ascendc-api-matmul-tiling.md` | 字节相同 | `d2d1a460951b3fbf013c01cd21a1ebeb7014b3501ff7681f36cb77524bdcf3f5` |
| `references/matmul/patterns.md` | 字节相同 | `b739769df779f5c97f2d689de57476c3a6d3cb45280a9e907eee86fb3ab19d33` |
| `references/reduction/alg-dichotomy.md` | 仅文末空行 | `86baec84fd2fef8a4ac897755ed3181855c6e33973bc9368f51e89548b2a0737` |
| `references/reduction/alg-group-reduce.md` | 仅文末空行 | `a093e609d217b38db7b739ff2f924e977d1b0abd6c5f18023623625cfebff5d5` |
| `references/reduction/alg-welford.md` | 字节相同 | `6c8e784dad546cb1caa07867596721b3d1c8ecc746396df5392054f44d84eb28` |
| `references/reduction/algorithms.md` | 字节相同 | `7d39036a799083c76990d1b4bee216b5fec8efd417f66f81ef824150270aa863` |
| `references/reduction/ara-fullload.md` | 字节相同 | `621e3770b5ad87c0a852eb639fac7bfea7b7c231380d66414aa2ba06cd50a1e2` |
| `references/reduction/ara-rowsplit.md` | 仅行尾空白 | `e7c5be5d9f510f22c989fa443a8dfe5e929312b2ccb82cb3cc59f2fdf83d9d25` |
| `references/reduction/multi-axis-transform.md` | 字节相同 | `2a18e0f523a8101607fc3fbe388517869ce25bd6d2f51be57444f46617f7d96f` |
| `references/reduction/multi-output-buffer.md` | 字节相同 | `e9d2991c887971a49b9cec263cb50ec94d6a0b731daed3ff10488d0106fb6d88` |
| `references/reduction/tiling-fields.md` | 字节相同 | `e0ad1169ab9272c9266922980da1b65863c64383b720704badba1fdde9e3f2f8` |

## 推理资料来源

这些输入身份来自原知识发行包的覆盖清单；保留其蒸馏、源码定位与阅读边界，不声称本次重新阅读了未分发的原文件。

| 原输入 | 原清单 SHA-256 | 知识正文 |
|---|---|---|
| 大模型推理 Vector 算子 Tiling 选型指南.md | `dc4efff1a86c3476eb228dadd3f065125211248a2b52e7edb1c9c088a8c5bbc7` | [vector-recipes.md](inference/vector-recipes.md) |
| 推理算子tiling分类.md | `fbd57e6a9c6fb0f79070819863e2d19411bc70d8df5129a2d1f8d81461fc970b` | [inference-routes.md](inference/inference-routes.md) |
| cann_vector_tiling_research_20260929.md | `265698d77b8d3ddcf8fa6fe3e5deeb679afac5d9c9a8c68608c4cc481a868592` | [vector-source-evidence.md](inference/vector-source-evidence.md) |
| add_rms_norm 算子 tilingKey 划分与启示.md | `37b0ecc01808d87c27ce7961e4f1bbdf255aa6ebdd93b4faff14e727649b09bd` | [add-rmsnorm-keys.md](inference/add-rmsnorm-keys.md) |

## 源码观察的历史证据

对应[十二样本源码观察](inference/vector-source-evidence.md)。原 2026-09-29 调研使用 `hicann` 镜像的 `ops-nn`、`ops-math` 与 `ops-transformer`；以下不可变内容仅供追溯，不作为 checkout、分支或当前实现的选择要求。正文用逻辑仓名、路径与符号定位，历史判断仍受各样本的阅读范围限制。

| 逻辑仓名 / 仓库内路径 | 原调研 blob |
|---|---|
| `ops-nn/activation/gelu/op_host/arch35/gelu_tiling_arch35.cpp` | [`c0d4347a8f6b19807ef6895e2ff3abd87fce538f`](https://api.github.com/repos/hicann/ops-nn/git/blobs/c0d4347a8f6b19807ef6895e2ff3abd87fce538f) |
| `ops-math/math/assign_sub/op_host/arch35/assign_sub_tiling_arch35.cpp` | [`e7b9487f89e63daea53b65e95438b9ee9dc4bee5`](https://api.github.com/repos/hicann/ops-math/git/blobs/e7b9487f89e63daea53b65e95438b9ee9dc4bee5) |
| `ops-math/math/add/op_host/arch35/add_tiling_arch35.cpp` | [`892b40b3d1953f4e3d9e453c19cf30e93ee41436`](https://api.github.com/repos/hicann/ops-math/git/blobs/892b40b3d1953f4e3d9e453c19cf30e93ee41436) |
| `ops-math/math/axpy_v2/op_host/arch35/axpy_v2_tiling_arch35.cpp` | [`71ce134a7385f4d2cca7f76b600ab34389720840`](https://api.github.com/repos/hicann/ops-math/git/blobs/71ce134a7385f4d2cca7f76b600ab34389720840) |
| `ops-math/conversion/clip_by_value/op_host/arch35/clip_by_value_tiling.cpp` | [`245798e17348fb48525b6ec587bbee91ebe94ef5`](https://api.github.com/repos/hicann/ops-math/git/blobs/245798e17348fb48525b6ec587bbee91ebe94ef5) |
| `ops-nn/norm/rms_norm/op_host/rms_norm_tiling.cpp` | [`e0245e4994f8dd8c01afc84db18084f001139853`](https://api.github.com/repos/hicann/ops-nn/git/blobs/e0245e4994f8dd8c01afc84db18084f001139853) |
| `ops-nn/norm/rms_norm/op_kernel/rms_norm_split_d.h` | [`6a52092764011cf5a6a16ed2dbafa70463462bb6`](https://api.github.com/repos/hicann/ops-nn/git/blobs/6a52092764011cf5a6a16ed2dbafa70463462bb6) |
| `ops-nn/norm/add_rms_norm/op_host/add_rms_norm_tiling_arch35.cpp` | [`96d108c31f2985a457366bce2b9200159473c1fd`](https://api.github.com/repos/hicann/ops-nn/git/blobs/96d108c31f2985a457366bce2b9200159473c1fd) |
| `ops-nn/norm/layer_norm_v3/op_host/arch35/layer_norm_v3_regbase_two_pass_tiling.cpp` | [`e768130c60ac9d6059e7c66ab5fc438c6afa8a42`](https://api.github.com/repos/hicann/ops-nn/git/blobs/e768130c60ac9d6059e7c66ab5fc438c6afa8a42) |
| `ops-nn/norm/layer_norm_v3/op_host/arch35/layer_norm_v3_welford_tiling.cpp` | [`077621e6937ddf7ff8e7b943a7a6c80206a5c79f`](https://api.github.com/repos/hicann/ops-nn/git/blobs/077621e6937ddf7ff8e7b943a7a6c80206a5c79f) |
| `ops-nn/activation/softmax_v2/op_host/arch35/softmax_v2_ar_full_load_tiling.cpp` | [`d95d6d98a14f9481a665852976875329fba9fc5b`](https://api.github.com/repos/hicann/ops-nn/git/blobs/d95d6d98a14f9481a665852976875329fba9fc5b) |
| `ops-nn/activation/softmax_v2/op_host/arch35/softmax_v2_ar_recompute_tiling.cpp` | [`438ba96f3fd64a8d436b480dffce597962f5f308`](https://api.github.com/repos/hicann/ops-nn/git/blobs/438ba96f3fd64a8d436b480dffce597962f5f308) |
| `ops-nn/activation/softmax_v2/op_host/arch35/softmax_v2_ara_full_load_tiling.cpp` | [`e4ef9ab6c65cd2635b0cbbce123b5bbc29f4643b`](https://api.github.com/repos/hicann/ops-nn/git/blobs/e4ef9ab6c65cd2635b0cbbce123b5bbc29f4643b) |
| `ops-nn/quant/dynamic_quant/op_host/dynamic_quant_tiling.cpp` | [`87a7f483a8637324b8a94c1405eb7b7cdb84c55f`](https://api.github.com/repos/hicann/ops-nn/git/blobs/87a7f483a8637324b8a94c1405eb7b7cdb84c55f) |
| `ops-nn/activation/swi_glu/op_host/swi_glu_tiling.cpp` | [`b495e91ea3669e67205a49d36eb33b797570ffc6`](https://api.github.com/repos/hicann/ops-nn/git/blobs/b495e91ea3669e67205a49d36eb33b797570ffc6) |
| `ops-transformer/posembedding/rotary_position_embedding/op_host/rope_regbase_tiling_ab.cpp` | [`625a7ac8be2ed68ed40b0a27719729536183897a`](https://api.github.com/repos/hicann/ops-transformer/git/blobs/625a7ac8be2ed68ed40b0a27719729536183897a) |

## 改编与许可边界

恢复时保留知识与必要案例，去除重复执行说明、实验报告、性能数据、试点通过率及轮次。历史 SDK/源码观察保留版本和原出处，不冒称目标版本事实；合成算例用于说明公式，不是设备验证。

本次静态审查澄清了完整归约后重算所需的信息保留、对齐后零 tile/空 tensor/整数上界、两类 Merge-row 任务口径，以及归并的路长/半区/同步边界。这些改编在对应正文给出，不以外部旧示例覆盖本地约束。

沿用原快照 CANN Open Software License Agreement 2.0 声明；[许可证副本](LICENSE-CANN-2.0.txt)随本目录安装，内容与仓库根 `LICENSES/CANN-2.0.txt` 相同。改编不改变原来源许可范围。本目录不分发 CANNBot 生成/进化插件、Hook、kernel 或实验资产。
