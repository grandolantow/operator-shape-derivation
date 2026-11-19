# 推导案例

以下示例演示应检查的关系，不提供跨算子通用公式。执行任务时使用目标版本的原始材料重新推导。

## A、B 组合成 C

用户说“给定 MatMul A 和逐元素 B，设计 C”。先检查 B 的输入绑定和函数：若 `C(X,W)=B(A(X,W))`，且 `A: [M,K] x [K,N] -> [M,N]`，则中间 Y 与输出 Z 通常为 `[M,N]`。如果 B 是 gated activation、沿 N 归约、带广播的残差或另一个分支，这个输出结论可能完全不同。

检查调用源码后再定接口。若 B 实际是把 Y 的末轴二分并做门控，则需要 Y 的宽度为 `2D`，W 对应 `[K,2D]`，C 输出为 `[M,D]`，同时核对 split 的具体排列与连续性。保留中间 Y 的规格，但除非用户需要，它不自动成为 C 的外部输入或输出。

这类例子适合验证 skill 是否真正检查消费关系，而非简单拼接 A、B 的用例。新 C 的 tiling 限制未知时，先产出语义合法的形状与尚未验证的实现约束。

## Compressor 案例提炼

一次 DeepSeek V4 Compressor 推导中，固定模型尺寸可从 config 和权重头得到，执行形状还依赖请求长度、图捕获对齐及同步结果。可迁移的检查包括：

- 实际请求 token、local graph 容量、跨 DP 同步结果、最终算子容量分列。实际 T32 映射 local T48 的案例里，缺少同步结果时不能直接给出最终 T48。
- 输出分配容量与有效输出数量使用不同公式；有效数量依赖各请求位置及 query 长度。有效输出为零仍可能执行 state 更新。
- 设备 block/page 表、物理 stride 与 cache shape 一起核对，避免单独覆盖其中一个标量后留下矛盾。
- checkpoint 的模型级 W4A8 标识不能决定每个 Compressor 张量的 dtype；分别读取权重头与接口要求。
- 启动脚本样例用于场景设计时标注假设，不能当作实际部署状态。测试用 state 池容量也不能冒充服务观测。
- 候选 graph 缺少实际请求和位置时，可以保留候选容量说明；不能伪造 metadata 后声称是观测 workload。

Compressor 的特定 H/R 限制、压缩比例、page/stride、图桶或容量公式必须留在该目标的推导产物中。不要复制到新算子的通用验证规则。

## Kimi K3 MlaPrologV3 漏推复盘

在本案例的归档 vLLM-Ascend 版本中，带 RoPE 的 strided cache writer 与主模型 Decode 融合入口共存。盲推把前者的 `use_mla_rope=True` 限制套到了后者，继而只追分解路线，漏查权重加载时的转置和补头。定位入口应从 `AscendMLAImpl.forward` 的实际分派开始，同时核对以下路线。

| 路线 | 生效条件与源码入口 | 推导到的实际权重和形状 |
| --- | --- | --- |
| 普通 Decode 分解 | `forward` 在融合等优先分支未命中时调用 `_mla_preprocess`。投影按逻辑 Q 头数 `H_q` 计算 | `q_b.weight [H_q×D_q,R_q]`，下游 FIA 前补齐 Q 的头轴 |
| BF16 Decode 融合 | `mla_preprocess_only_decode` 调用 `cann_ops_transformer.mla_prolog`。本 BF16 路线核对生效的 `enable_mlapo`、原生权重支持、纯 Decode、token 上限、缓存/并行限制及 gate 布局。NoPE 时 Python caller 可传 `rope_sin=None`、`rope_cos=None` | `_process_weights_for_fused` 先转置权重，展开为 `[R_q,H_q,D_q]`，在头轴补零后展平为 `weight_uq_qr [R_q,H_pad×D_q]`。配套的 `weight_uk` 和融合输出的头轴也使用 `H_pad`，调用者随后裁回 `H_q` |

这里 `R_q` 是 Q 的压缩维度，`D_q` 是 Q-B 投影的单头宽度，`H_pad` 是后端对齐后的头数。模型配置与源码可支撑两条路线的条件推导，实际启用状态需要同次启动配置或调用证据。代码定位在 `attention/mla_v1.py` 的 `process_weights_after_loading`、`_process_weights_for_fused`、`mla_preprocess_only_decode` 与 `forward`。本例的头数、对齐规则以及 wrapper 条件均以目标版本源码为准。

旧 FP8 采集中，`MlaPrologV3` 权重描述符已经展示融合接口的轴顺序。采集中的 `Transpose` 经前后调用与 shape 核实作用于 AllGather 后的激活。BF16 权重的转置和补头从加载函数追到 `weight_uq_qr`，具体结果由 BF16 路线源码和模型配置推导。

## 缺少 profiling

用户只给模型配置和源码，未说明是否有 profiling：先请求已有采集路径及对应运行配置，同时完成固定维度和符号接口；不因为问询超时而开始假设完整 workload。

若配置中已明确指定测试用例（例如 `test_tokens=[1,17,64]`），这些已给定的值可用于推导和导出，来源标为用户测试配置。继续索取 profiling，但不等待它才处理已知用例；尚未给定的范围、metadata 和观测频率不能因此自行补齐。

用户明确“没有 profiling，按配置设计用例”：不重复索取。采用已知参数范围选择代表/边界场景，逐项标注测试假设，频率和 latency 为空。必要参数完全缺失时，解释可采用的假设或保留待定，不套用 Compressor 的经验数值。

用户提供只有 kernel 名称和耗时的 CSV：核对是否能匹配目标，但不能称已经观测到 shape。请求带 shape/metadata 的相关材料；若用户确实没有，再进入上述场景生成路径。
