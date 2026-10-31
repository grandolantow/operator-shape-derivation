# 从源码到 kernelbench

## 1. 接收材料

记录源入口与 revision/文件哈希、参数签名、计算链、可变状态与已有实现路径。输入只有 `.cpp` 时，还需定位注册/host/tiling/调用封装；不能假定它是可执行独立工程。Triton 输入定位 wrapper、launch grid及torch前后处理；torch组合保留完整运算顺序和舍入点。

在 sources 记录 profiling 采集配置、rank/step、计时层级。未提供 profiling 时按 shape skill 的证据规则处理，不补造生产频率；用户指定具体测试 shape 可直接使用并标记来源。

## 2. 数据包内容

| 产物 | 最小内容 |
|---|---|
| definition | 实际 schema 的输入/输出/轴/dtype/约束与 reference 接入 |
| workload | 每例稳定 ID、具体 axes、参数、输入构造描述 |
| manifest | IDs、来源、推导/假设、功能覆盖、seed与输入关联 |
| inputs | 关联metadata/索引/state构造和reset；无需时可采用框架标准输入生成 |
| reference | 原始数学语义/依赖与独立正确性参照的定位 |
| runner | 计时边界、状态恢复、warmup；正确性全量、性能固定10例（超大≤3）；可复用已验证runner |
| contract | 精度/数值语义、正式性能协议、支持域、基线、资源边界 |

读取目标仓库的 schema 和 loader，不假定 workload 必须叫 `.json` 或 `.jsonl`，也不通过物理行数判断 case 数。保留 definition/workload 的原生布局，将额外 manifest 放在 loader 不会误识别的位置。

若当前生成器入口是 `model.py/get_inputs` + JSON case，需要写显式适配器；记录每个原case ID→生成器组号映射。接口参数顺序、dtype、stride、状态和随机数来源保持一致。包装层不能添加影响语义的 `.contiguous()` 或把动态计算搬到计时外。

## 3. 部署与检查

根据当前仓库类别核实 Level（常见 L1基础Vector/L2融合/L3Cube/L4CV），创建独立 problem 名称。不得覆盖同名既有任务。先在独立 staging 校验 schema，再用真实 Problem/Workload loader 读取；支持CPU的输入构造用小代表case做shape/dtype/stride检查。记录真实调用入口、退出码、caseIDs和所有限制。

生产运行还必须验证目标设备格式和基线。有状态任务检查同S0重放、未触碰页、输出padding、不可变输入；ND/NZ与FP4等真实物理表示由目标环境适配器验证，CPU随机输入不等价于真实格式。

新建或修复 runner 时，先检查参数传递、哈希/汇总、空有效区与失败传播，再进入设备验证。候选运行前生成独立 golden 并冻结输入指纹；保留容量，只比较定义有效区；空有效区仍实际调用组件并验证合同要求。图模式要检查真实动态 metadata 更新后的重放。原始 R 也须通过正确性，异常和原 verifier 失败必须传播到结果；smoke/self-check不能冒充正式全量通过。

计时归档写清捕获范围、每图调用次数、replay方式、warmup、Event/PMU指标及聚合公式。搜索计时、eager诊断、正式图模式各自单列；异常大收益先核对原始样本、单位、case及库身份。图重放时间不能无证据地解释为纯kernel时间，也不扣除推测的固定开销。

冻结后如发现数据包错误，建立新修订并重新生成相关结果，不悄悄覆盖旧workload。资源不足可保留blocked case，不能缩小shape后沿用同case ID宣称全量通过。

## C/V 组件数据包

进入 [C→V 串行分支](cv-serial.md)时，从父 workload 派生 C、V 的 definition/workload/reference 与输入构造，按实际仓库规范放入独立目录并分别验证 loader。组件形状由计算边界推导，不能只复制父输入 shape。

manifest 保留 `parent_case_id`、组件 case ID、输入/metadata/seed 来源、边界修订；分 chunk 时补覆盖范围、执行顺序、尾块和合并规则。组件测量可按等价结构分组筛选，但父任务正确性覆盖原完整case，性能覆盖冻结的10例及既定权重，每个被测父case的完整工作量均须保留。新增邻近shape作为独立正确性覆盖集，不混入原始性能分母。

V 的独立输入由 reference 或已核实 fixture 生成；实际 C→V 组合另测。对齐逻辑/物理布局、舍入及有效区，不能通过额外 contiguous/pad/cast 偷换合同。完整 runner 负责所有 chunk 和实时适配，部署组件问题不代表父算子已经通过。
