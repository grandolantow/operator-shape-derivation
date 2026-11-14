# 四份知识输入的覆盖核对

| 用户提供的原文件 | SHA256 | 上一版 | 现在可读的位置 |
|---|---|---|---|
| 大模型推理 Vector 算子 Tiling 选型指南.md | `dc4efff1a86c3476eb228dadd3f065125211248a2b52e7edb1c9c088a8c5bbc7` | 仅通用依赖/预算；未系统区分六种基础切分与条件策略 | [vector-recipes.md](vector-recipes.md) |
| 推理算子tiling分类.md | `fbd57e6a9c6fb0f79070819863e2d19411bc70d8df5129a2d1f8d81461fc970b` | 五类主导依赖不能替代十类推理场景 | [inference-routes.md](inference-routes.md) |
| cann_vector_tiling_research_20260929.md | `265698d77b8d3ddcf8fa6fe3e5deeb679afac5d9c9a8c68608c4cc481a868592` | 没有十二样本逐项出处和观察边界 | [vector-source-evidence.md](vector-source-evidence.md) |
| add_rms_norm 算子 tilingKey 划分与启示.md | `37b0ecc01808d87c27ce7961e4f1bbdf255aa6ebdd93b4faff14e727649b09bd` | 没有按架构区分 key 与参数的实例 | [add-rmsnorm-keys.md](add-rmsnorm-keys.md) |

范围：保留选型条件、反例、样本来源和版本边界，不复制本地图片、不将评分或样例阈值写成门禁。研究建议不等于本轮 benchmark 的已证收益。
