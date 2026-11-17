# Tiling 知识的来源与维护

## 引用约定

- 本地知识由本仓维护，按 [INDEX.md](INDEX.md) 读取；策略优先级见[生成设计评审](../generation-design-review.md#知识来源与策略优先级)。
- CANNBot 的 `references/...` 相对其 `ops/ascendc-tiling-design/`。checkout 沿用[执行适配](../cannbot-execution.md#路径与安装)中的 `cannbot_root` / `CANNBOT_SOURCE_ROOT`；目录变化时从该 checkout 的实际技能索引定位同主题资料。
- 历史提交与 blob 仅供追溯，不要求任务使用该镜像或版本。任务记录实际来源与版本；外部内容变化时核对差异及适用域，缺失资料记录具体缺口。

## 知识来源

本地知识改编自 [PR #6 的知识快照](https://github.com/lanhongsheng/operator-shape-derivation/tree/2619c00f74997b7d4b23ae86a77529ddc5ff0416/skills/ascend-op-workflow/references/tiling-knowledge)。除归并边界卡外，正文对应原快照的 `references/<当前卡片路径>`；API 精度注记另合并原 `sort/patterns.md`、`sort/alg-two-level-mrgsort.md`、`reduction/with-index.md` 的限定增量，归并边界卡基于原 Sort 两卡补充边界推导。

重复基础正文已与 CANNBot 历史提交 `bcb8067bd6ebab19e490b317ad8250e25a18316b` 的 tiling 目录逐项核对，按 INDEX 和卡片中的 CANNBot 路径引用；本地保留增强知识。


## 推理资料来源

以下原始资料名称及对应关系来自知识快照的覆盖清单；正文保留蒸馏与源码阅读边界，不声称重新读取了未分发的原始文件。

| 原始资料 | 知识正文 |
|---|---|
| 大模型推理 Vector 算子 Tiling 选型指南.md | [vector-recipes.md](inference/vector-recipes.md) |
| 推理算子tiling分类.md | [inference-routes.md](inference/inference-routes.md) |
| cann_vector_tiling_research_20260929.md | [vector-source-evidence.md](inference/vector-source-evidence.md) |
| add_rms_norm 算子 tilingKey 划分与启示.md | [add-rmsnorm-keys.md](inference/add-rmsnorm-keys.md) |

## 源码观察的历史证据

对应[十二样本源码观察](inference/vector-source-evidence.md)。原 2026-09-29 调研使用 `hicann` 镜像的 `ops-nn`、`ops-math` 与 `ops-transformer`；以下不可变内容仅供追溯，不作为 checkout、分支或当前实现的选择要求。正文用逻辑仓名、路径与符号定位，历史判断仍受各样本的阅读范围限制。

| 逻辑仓名 / 仓库内路径 | 原调研 blob |
|---|---|
| `ops-nn/activation/gelu/op_host/arch35/gelu_tiling_arch35.cpp` | [历史内容](https://api.github.com/repos/hicann/ops-nn/git/blobs/c0d4347a8f6b19807ef6895e2ff3abd87fce538f) |
| `ops-math/math/assign_sub/op_host/arch35/assign_sub_tiling_arch35.cpp` | [历史内容](https://api.github.com/repos/hicann/ops-math/git/blobs/e7b9487f89e63daea53b65e95438b9ee9dc4bee5) |
| `ops-math/math/add/op_host/arch35/add_tiling_arch35.cpp` | [历史内容](https://api.github.com/repos/hicann/ops-math/git/blobs/892b40b3d1953f4e3d9e453c19cf30e93ee41436) |
| `ops-math/math/axpy_v2/op_host/arch35/axpy_v2_tiling_arch35.cpp` | [历史内容](https://api.github.com/repos/hicann/ops-math/git/blobs/71ce134a7385f4d2cca7f76b600ab34389720840) |
| `ops-math/conversion/clip_by_value/op_host/arch35/clip_by_value_tiling.cpp` | [历史内容](https://api.github.com/repos/hicann/ops-math/git/blobs/245798e17348fb48525b6ec587bbee91ebe94ef5) |
| `ops-nn/norm/rms_norm/op_host/rms_norm_tiling.cpp` | [历史内容](https://api.github.com/repos/hicann/ops-nn/git/blobs/e0245e4994f8dd8c01afc84db18084f001139853) |
| `ops-nn/norm/rms_norm/op_kernel/rms_norm_split_d.h` | [历史内容](https://api.github.com/repos/hicann/ops-nn/git/blobs/6a52092764011cf5a6a16ed2dbafa70463462bb6) |
| `ops-nn/norm/add_rms_norm/op_host/add_rms_norm_tiling_arch35.cpp` | [历史内容](https://api.github.com/repos/hicann/ops-nn/git/blobs/96d108c31f2985a457366bce2b9200159473c1fd) |
| `ops-nn/norm/layer_norm_v3/op_host/arch35/layer_norm_v3_regbase_two_pass_tiling.cpp` | [历史内容](https://api.github.com/repos/hicann/ops-nn/git/blobs/e768130c60ac9d6059e7c66ab5fc438c6afa8a42) |
| `ops-nn/norm/layer_norm_v3/op_host/arch35/layer_norm_v3_welford_tiling.cpp` | [历史内容](https://api.github.com/repos/hicann/ops-nn/git/blobs/077621e6937ddf7ff8e7b943a7a6c80206a5c79f) |
| `ops-nn/activation/softmax_v2/op_host/arch35/softmax_v2_ar_full_load_tiling.cpp` | [历史内容](https://api.github.com/repos/hicann/ops-nn/git/blobs/d95d6d98a14f9481a665852976875329fba9fc5b) |
| `ops-nn/activation/softmax_v2/op_host/arch35/softmax_v2_ar_recompute_tiling.cpp` | [历史内容](https://api.github.com/repos/hicann/ops-nn/git/blobs/438ba96f3fd64a8d436b480dffce597962f5f308) |
| `ops-nn/activation/softmax_v2/op_host/arch35/softmax_v2_ara_full_load_tiling.cpp` | [历史内容](https://api.github.com/repos/hicann/ops-nn/git/blobs/e4ef9ab6c65cd2635b0cbbce123b5bbc29f4643b) |
| `ops-nn/quant/dynamic_quant/op_host/dynamic_quant_tiling.cpp` | [历史内容](https://api.github.com/repos/hicann/ops-nn/git/blobs/87a7f483a8637324b8a94c1405eb7b7cdb84c55f) |
| `ops-nn/activation/swi_glu/op_host/swi_glu_tiling.cpp` | [历史内容](https://api.github.com/repos/hicann/ops-nn/git/blobs/b495e91ea3669e67205a49d36eb33b797570ffc6) |
| `ops-transformer/posembedding/rotary_position_embedding/op_host/rope_regbase_tiling_ab.cpp` | [历史内容](https://api.github.com/repos/hicann/ops-transformer/git/blobs/625a7ac8be2ed68ed40b0a27719729536183897a) |

## 许可

沿用 CANN Open Software License Agreement 2.0；[许可证副本](LICENSE-CANN-2.0.txt)随本目录安装，内容与仓库根 `LICENSES/CANN-2.0.txt` 相同。改编不改变原来源许可范围。本目录不分发 CANNBot 生成/进化插件、Hook、kernel 或实验资产。
