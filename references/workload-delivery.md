# Workload 与输入生成器交付

## 目标目录与结构化结果

先检查已有入口和目标 benchmark，沿用已存在的命名和 schema。新目录可以采用以下紧凑结构，按实际需要合并脚本，避免空文件和重复说明：

- `shape_derivation.md`：目标接口、公式、证据、假设、覆盖与适用范围。
- `shape_results.json`：结构化推导结果。
- `derive_shapes.py`：读取配置、重算形状及选择用例；可同时导出 workload。
- `workload.jsonl`：目标框架可解析的用例。
- `workload_manifest.json`：case 与具体输入规格、原始结果和选择理由的映射。
- `workload_inputs.py`：框架需要的自定义输入构造；常规 descriptor 已足够时提供简洁的构造/验证入口，避免另造不兼容的数据格式。
- 目标专用测试或验证命令；有必要保存的原始证据放在 `evidence/`。

结构化结果至少表达下列信息；可沿用已有 schema，不强制采用固定层级：

| 信息 | 要求 |
|---|---|
| target | 算子/组合关系、外部与中间接口、设备/版本、阶段 |
| sources/config | 原始值、来源定位及最终生效值；区分脚本示例 |
| tensors | shape、dtype、layout/stride/offset（适用时）、输入输出或状态角色 |
| dependencies | 符号、公式、合法性约束、推导依赖与适用前提 |
| cases | 稳定 id、具体参数、metadata 生成规则、来源类别和保留理由 |
| observation | 样本次数、分母、采集范围；未观测则 null |
| unresolved/skipped | 未确定字段、缺失依据、未导出原因 |
| validation | 实际执行的检查及未执行层级 |

shape 数据保留符号/未知状态；导出 runnable case 时所有必要字段必须具体化。生成脚本接受外部配置，不把案例模型或本机路径写成通用默认。配置/算法不变时重跑不应改变内容或 UUID；时间戳等运行信息单独记录。

## npu-kernelbench 适配

定位用户实际使用的 checkout，读取其 `src/npu_kernelbench/data/workload.py`、`definition.py` 和 evaluator 输入生成实现，记录 revision/相关差异。也可使用用户提供的 schema 快照；框架缺失且无法读取时先索取位置，完成框架无关产物，不宣称 schema 已通过。

已有版本采用 `uuid / axes / inputs`，并支持 random、scalar、custom、safetensors、tensor_list 等描述符。这些是定位提示，不是冻结的 API；按当前实现验证字段、禁止混用的类型、轴解析和默认容差行为。

- 核对 workload axes 与 definition 的合法轴、输入名称/类型、符号解析一致。仅在需要区分同 shape 不同 metadata 时采用稳定的 case 轴；新增轴需列明对 definition 的接入要求。
- 普通 random 能表达 dtype/shape 不等于能表达关联 metadata。固定 tensor 数值不能仅因 scalar 支持 list 就当作 tensor 输入。
- 需要自定义构造时，读取 callback 的真实签名、返回类型和调用生命周期。已有接口形如 `make_inputs(resolved_axes, device)` 返回输入字典；不要未经核对假设每次 benchmark 只调用一次，或永远按每个输入重复调用。
- 若当前路径按每个输入重调完整 callback，同一 case 的关联输入必须来自一致的生成规则，不能分别消耗全局 RNG 后破坏对应关系。callback 接收不到 seed/uuid 时，从明确的 case 配置绑定确定性 seed；不要伪造 callback 参数。采用缓存需定义失效/reset，不能跨执行复用已修改的 state。
- definition/reference 已存在时检查 custom entrypoint 的装载位置和名称。缺失时给出所需输入名、轴、入口及导入说明，不在默认范围内新建或修改 definition/reference。
- 不为让 schema 通过而放宽精度门槛；框架自带默认值不等于用户确认的精度契约。未明确时在接入缺口中记录待核对的容差/检查范围。
- 没有真实同条件测量时，性能基线缺省或 null；不得用猜测 latency 填充评分字段。

用户指定其他 benchmark 时，同样从其 schema、输入构造生命周期与 runner 约定设计适配；不要将 npu-kernelbench 字段强塞入目标格式。

## 输入生成语义

生成器应输出满足接口的数据，而不仅是正确维度的随机 tensor：

- 关联 metadata 成套生成并验证，例如 cu lengths 单调且末项正确、路由计数与总量一致、block id 不越界、有效请求与 dummy 请求区分。
- shape、dtype、stride、storage offset/format、别名及布局一致。需要非连续 view 或共享 backing storage 时显式构造；不能默认 clone 会保留全部物理关系。
- 用稳定 seed/独立随机生成器复现数据；记录分布及输入数值约束，不声称合成输入等于线上数据。
- 对用户已指定的测试用例，可选择并记录接口允许的合成数值分布、seed 和输入构造布局；这些测试构造设置不需要伪造 profiling 来源。若缺失的是决定形状、有效工作量或合法性所必需的 metadata，则仍须补充证据或按用户已允许的假设处理。
- 对可写 state，提供明确的 fresh/reset 机制，reference、candidate、重复执行之间不能误复用已修改状态。若框架缓存、复制或重建输入，核对该路径是否保留所需 stride 和别名。
- 单次输入生成不能解决 runner 在 reference/candidate/计时循环间直接复用可写输入的问题。若实际 runner 没有 reset 接线，明确标注状态隔离尚未接入；默认交付可提供所需 helper 和接入说明，但不能宣称正确性或计时状态已隔离，也不自行修改 evaluator。
- 合理估算单 case 内存；逻辑表宽、活跃页数和物理 state 池分别计算。独立测试池可以用有依据的测试假设，但不能冒称真实服务分配。
- 未知真实 metadata 时可以生成合法测试数据，但需符合用户允许假设的前提，并标为合成。无法具体化的必要字段不自动填默认值。

## 验证与重跑

1. 以原始配置、权重头、源码公式/约束或 profiling 记录核对关键字段。不要只让两个复制同一公式的脚本相互证明。
2. 测试目标相关边界和拒绝非法输入；对组合接口检查轴连接、广播、dtype 与状态兼容性。随机测试只在确实补充边界覆盖时使用。
3. 用当前框架 schema 解析 workload；有 definition 时再检查 axes/inputs/entrypoint 的兼容性。记录缺失项而不是创建超出范围的参考实现。
4. 确定性重生成，与 manifest、case id、源结果逐条核对；skipped 用例应能说明为什么不能导出。
5. 现有依赖与资源允许时，实际调用生成器，验证张量规格、metadata 边界、fresh/reset 与可写状态隔离。对同一固定 shape 的测试无需无意义穷举；不要为完成此步自行安装框架或申请未指定远端。
6. 给出正确的重跑命令、参数来源和工作目录。分别报告静态检查、schema、输入构造、算子/NPU与性能检查；未运行层级保持明确。

用户后续要求完整执行 benchmark、reference、内核或采集时，按新增授权继续对应任务；不能从本 skill 的默认范围推断这些工作已完成。
