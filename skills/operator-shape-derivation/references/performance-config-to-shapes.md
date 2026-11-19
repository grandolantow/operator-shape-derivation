# 由性能配置定位 shape

性能出口表中的同一行可以覆盖多个 rank、执行阶段和调度步。先确定目标算子所在的模型、P/D 侧、rank、层和调用分支，再将配置字段接到具体的张量轴。只提取影响目标的字段。

## 性能表字段

| 常见字段 | 影响的 shape 或运行条件 | 核对材料 |
| --- | --- | --- |
| 产品形态、模型和参数配置 | 模型决定 hidden、head、专家及 FFN 轴。量化、设备和后端决定打包权重、scale、融合分支及物理布局 | 模型及 draft config、权重元数据、loader、当前算子接口 |
| 场景、组网、卡数、P/D 卡数 | P/D 各侧的分片、KV 传输及 collective 的 payload。总卡数相同可对应多种运行分组 | 各侧有效 TP、DP、EP、PP、CP 配置、实际组成员及通信后端 |
| 序列、上下文长度、平均输入 | 本步新算的 token 数影响 GEMM 的 M 和 Attention 的 Q 轴。可见历史长度影响 KV 寻址和工作量，描述符是否随之变化取决于缓存形状和 padding | 实际输入长度分布、每步 Prefill chunk、每请求有效 KV 长度、block table 的使用范围和分配宽度 |
| 平均输出 | 影响请求存活多少轮、KV 增长及不同 Decode shape 的出现频率 | 实际输出长度、每请求 Decode 轮数和逐步历史长度 |
| Prefix Cache 开关、配置命中率 | 复用已命中的 KV 可以减少 Prefill 新算行数。后续 Attention 可以读取这些历史 KV | 先确认命中率按请求还是按 token 统计，再取实际命中 token 数、剩余输入及 chunk。按当前实现核对页对齐和重算 |
| 最大并发、系统并发、请求频率、总请求数 | 经排队、路由和动态组批影响每 rank 每步的活跃请求数和 token 行数 | 服务侧 `max_num_seqs`、`max_num_batched_tokens` 等上限，实际调度量和 graph 补齐量。客户端并发、运行上限、实际 batch 分别记录 |
| 采信率 | 如指投机接受率，影响提交 token 数、后续轮数、状态更新。动态投机还可能变化后续草稿长度 | 实际 draft、verify、accepted 各自的 token 数，动态调整条件 |
| TTFT、TPOT、ITL、E2E、吞吐、QPS、QPM、截图 | 用于验收和结果归因 | 用同次运行标识、rank/step 和 case 索引连接归档数据及 profiling |

上下文长度还可能指服务上限 `max_model_len`。根据字段含义区分它与请求实际长度。将有效 KV token 数、block table 使用范围、单页槽数和预分配页数分别记录。使用固定容量或图桶时，逻辑长度变化可以只反映在长度张量的值和有效数据范围。

## 并行与投机推理

| 策略 | 优先核对的轴与分支 |
| --- | --- |
| TP | 列并行通常分输出宽度，行并行通常分输入宽度。核实本地 weight 参数布局、局部 Q/KV heads、FFN 和词表的分片或复制。Sequence Parallel 开启时进一步跟踪 token 轴、padding 和 gather/reduce-scatter 前后边界 |
| DP | 纯 DP 复制模型权重，副本独立组批。记录每个副本的请求数和有效、执行 token 数。DP 参与专家并行分组时，也会影响专家分片 |
| EP | 本地专家数决定权重专家轴及部分 metadata 长度。记录本地专家映射、冗余和负载均衡，以及 dispatch 容量、每专家有效行数、`group_list` 表示。常见 vLLM 配置的 EP 组可由 TP×DP 组成，具体以实际运行分组为准 |
| PP | 每个 stage 的层范围、首尾 stage 特有算子、跨 stage 张量及 microbatch。固定层、TP 和步内 token 数时，层内张量关系通常沿用原公式 |
| PCP / DCP | 长上下文 Prefill 的 Q/KV 分片、Decode 的历史 KV 分片、不同 Attention 分支的局部 Q head 数及后续归并。区分页大小、页数和有效长 |
| MTP | MTP 草稿路径可逐步生成候选。固定候选数 `k`、每个请求的 Verify 包含一个额外位置时，`B` 个请求的有效 Verify 行数为 `B*(k+1)`。候选数随请求变化时，按接口实际接收的 token 求和，再单独处理图桶补齐 |
| DSpark | 核对 drafter 的模型、分片、块长和生成方式。分别追踪 draft context、draft query 和 target verify 的 token 轴。与 MTP 采用相同候选数时，仍应按各自的实现推导草稿输入、权重和 KV |

## 接到推导与用例

- **配置**记录模型及量化版本、P/D 各侧实际并行组、投机方法与预算。**容量**记录调度预算、图桶、KV 分页和 dispatch 分配上限。**实况**记录每步每 rank 实际有效量、补齐量和有效 metadata。对每个目标轴保留具体来源及适用条件。
- 用同次采集关联 rank、step、分支、算子和 case，保留不同 shape 的频率及采样范围。性能表里的平均值可以描述场景，具体 shape 仍按当前证据或明确约定生成。
- 同一步的 FlashMLA history 和 current 调用可能采用不同的本地 Q 头数。沿各自输入 view 和后端分支确认 head 轴。MoE 权重的本地专家轴、GMM 接收的行容量及 `group_list` 表示的有效行数，分别沿权重分片、dispatch 分配和专家路由确认。

接口和配置随版本变化。查阅相关文档后，回到目标环境的代码和生效配置核对。[vLLM 调度参数](https://docs.vllm.ai/en/latest/configuration/engine_args/) · [Prefix Caching](https://docs.vllm.ai/en/stable/features/automatic_prefix_caching/) · [Expert Parallel](https://docs.vllm.ai/en/latest/serving/expert_parallel_deployment/) · [Context Parallel](https://docs.vllm.ai/projects/ascend/en/main/developer_guide/Design_Documents/context_parallel.html) · [Ascend 投机推理](https://docs.vllm.ai/projects/ascend/en/main/user_guide/feature_guide/speculative_decoding.html)
