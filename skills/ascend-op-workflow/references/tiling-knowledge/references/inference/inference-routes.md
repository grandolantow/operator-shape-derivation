# 推理场景：语义边界比名字更重要

沿用已有类别指南，下表只导航到值得评估的分支，不为每个名字增加 kernel 或门禁枚举。示例是设计起点，不代表所有示例已有该实现。

| 算子类型| 代表性算子 | 常用 tiling | 适用 shape |
|---|---|---|---|
| 逐元素类 | Add、Mul、Cast；Gelu、Swish（SiLU） | Flatten / 连续分块 | 连续且元素独立，如 `[2048,4096]`，可展平分块 |
| 逐元素类 | Add、Mul、Cast；Gelu、Swish（SiLU） | FullLoad / 少核 | 总工作集小，如 `[1,256]`、`[4,128]` |
| 逐元素类 | Add、Mul、Cast；Gelu、Swish（SiLU） | 核内循环分块 | 单核负责的数据超过 UB 容量，如大规模激活 `[8192,4096]` |
| 广播类 | BiasAdd、Mul（广播）；Quantize / Dequantize（给定 scale） | MergeN / 参数复用 | 多行共享短参数，如 `[8192,128]` 与 `[128]` 运算 |
| 广播类 | BiasAdd、Mul（广播）；Quantize / Dequantize（给定 scale） | 二维分块 | 行列都较大，如 `[2048,4096]` 与 `[4096]` 运算 |
| 广播类 | BiasAdd、Mul（广播）；Quantize / Dequantize（给定 scale） | SplitD | 特征维长，整行工作集放不下，如 `[128,32768]` 与 `[32768]` 运算 |
| 配对 / 门控类 | SwiGlu、RotaryPositionEmbedding；inplace_partial_rotary_mul | MergeN / 合并 head | 每行或每个 head 较短，如 RoPE `[128,32,128]` |
| 配对 / 门控类 | SwiGlu、RotaryPositionEmbedding；inplace_partial_rotary_mul | 按 token / head 分块 | token、head 可独立计算，如 RoPE `[1,64,128]`，可利用 64 个 head 的并行性 |
| 配对 / 门控类 | SwiGlu、RotaryPositionEmbedding；inplace_partial_rotary_mul | 二维分块 / SplitD | 门控特征维长，如 SwiGLU `[1024,22016] → [1024,11008]`；每个 tile 必须取得对应的两路数据 |
| 尾轴规约类（含规约后处理） | RmsNorm、LayerNorm、SoftmaxV2；add_rms_norm_bias、rms_norm_cast | MergeN | 短行且行多，如 `[8192,128]` |
| 尾轴规约类（含规约后处理） | RmsNorm、LayerNorm、SoftmaxV2；add_rms_norm_bias、rms_norm_cast | FullLoad | 整行工作集可放下，如 `[2048,4096]` 的候选场景 |
| 尾轴规约类（含规约后处理） | RmsNorm、LayerNorm、SoftmaxV2；add_rms_norm_bias、rms_norm_cast | 核内 SplitD / Recompute | 超长行或融合后工作集过大，如 `[128,131072]` |
| 尾轴规约类（含规约后处理） | RmsNorm、LayerNorm、SoftmaxV2；add_rms_norm_bias、rms_norm_cast | 跨核 SplitD + 统计合并 | 行数少且单行极长，如 `[1,131072]`；需评估额外合并成本 |
| 非尾轴规约类 | SoftmaxV2（RA / ARA 路径） | ARA FullLoad | `[A₁,R,A₀]` 沿 R 规约，R × 内层切片的工作集可放下，如 `[32,128,128]` 沿 axis=1 |
| 非尾轴规约类 | SoftmaxV2（RA / ARA 路径） | ARA Recompute / 规约轴分段 | R 较长，全载工作集放不下，如 `[32,16384,128]` 沿 axis=1 |
| 动态量化类（含量化融合） | DynamicQuant；rms_norm_dynamic_quant、swiglu_group_quant、dequant_swiglu_quant | MergeN / 合并量化组 | 短行或短组数量多，如 `[8192,128]`；分组量化逻辑 shape `[2048,32,128]` |
| 动态量化类（含量化融合） | DynamicQuant；rms_norm_dynamic_quant、swiglu_group_quant、dequant_swiglu_quant | 逐行 / 逐组 FullLoad | 完整统计域可放下，如逐 token 量化 `[2048,4096]` 的候选场景 |
| 动态量化类（含量化融合） | DynamicQuant；rms_norm_dynamic_quant、swiglu_group_quant、dequant_swiglu_quant | SplitD / 分阶段统计与量化 | 统计域过长或融合工作集过大，如逐行量化 `[128,32768]`；不能改变原量化组边界 |
| 索引搬运 / 重排类 | GatherV2、MoeInitRouting；scatter_nd_update_sk、copy_and_expand_eagle_inputs | 按索引 / 行分核 | 索引数量多，如从 `[V,4096]` 中 Gather 2048 行 |
| 索引搬运 / 重排类 | GatherV2、MoeInitRouting；scatter_nd_update_sk、copy_and_expand_eagle_inputs | MergeN / 多行搬运 | 搬运行短，如输出 `[8192,128]`；需支持对应的离散地址访问 |
| 索引搬运 / 重排类 | GatherV2、MoeInitRouting；scatter_nd_update_sk、copy_and_expand_eagle_inputs | 按行 + SplitD | 搬运行宽，如输出 `[128,32768]`，将每行拆成连续片段 |
| 转置 / 布局变换类 | transpose_kv_cache_by_block、kda_layout_swap12 | 局部块 FullLoad | 完整转置块及临时量可放下，如局部 `[128,128]` 矩阵 |
| 转置 / 布局变换类 | transpose_kv_cache_by_block、kda_layout_swap12 | 二维 / 多维分块 | 整体数据较大，如 `[4096,4096]` 转置，或多维张量交换两个轴 |
| 排序 / 选择类 | moe_gating_top_k、moe_gating_top_k_hash；TopKTopPSample | FullLoad | 每行候选域较小，如路由 `[2048,256]`，每行选 8 个 expert |
| 排序 / 选择类 | moe_gating_top_k、moe_gating_top_k_hash；TopKTopPSample | MergeN | 候选域短且行数多，如 `[8192,32]`，每行选 2 个；需匹配具体模板支持 |
| 排序 / 选择类 | moe_gating_top_k、moe_gating_top_k_hash；TopKTopPSample | 分段选择 / 排序 + 合并 | 候选域很大，如词表 `[4,131072]` 做 TopK；TopP 还需概率累计 |
| 扫描 / 累积类 | Cumsum；kda_gate_cumsum_vllm | 短序列 / chunk 全载 | 扫描长度短，如逻辑 `[T,H,D]=[64,16,128]`，按 head/channel 切分后处理时间轴 |
| 扫描 / 累积类 | Cumsum；kda_gate_cumsum_vllm | 时间分块 + 局部扫描 | 时间轴长，如 `[4096,16,128]`；全局 Cumsum 需跨块前缀传播，chunk 内 Cumsum 按块重置 |

**落实到实现前的检查。** RoPE 必须保持相邻或半区配对，SwiGLU 的两路特征要同时可取；动态量化要保持 per-token/per-group 统计域、scale 写出及打包边界；Norm/Softmax 先取得完整统计再输出。Gather、分页 KV 与 MoE 重排核实 page/slot/expert 映射、离散行与连续片段。KV 转置计入二维块、临时量和尾块。TopK 分段后再归并，TopP 还需概率累计与截断，MoE gating 保留分组和归一化语义。扫描先区分 chunk 内重置与全局跨块前缀；这里只描述算法知识，不是本次 Cumsum 设备结论。

**哪些可复用原仓？** 原对照基于 hicann/cannbot-skills 的 80bd6c22，而非当前发行版的缺失清单。逐元素、广播、AR/ARA、Group Reduce、排序及部分 Gather/前缀方法已有基础。不要另造同名算法；重点补配对/融合、分段输出、Merge-row 选择和推理索引映射。使用现场版本已有的分类；未匹配可走 generic，仍须保留上述语义约束。
