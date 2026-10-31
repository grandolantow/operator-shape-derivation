# 实现前的生成设计评审

用于新生成、缺失组件适配或主要计算路线变更。在外部合同及 workload 已明确后、批准实现前完成；不修改 CANNBot 角色/模板，将本要求作为 workflow 的任务附件传给原生设计、独立走读和开发角色。完整复用工程路线未变且证据有效时无需重做；已有 run 的冻结合同与 G 不追溯改写。

## 设计前核查路线

先从数学和实际支持域识别主要计算，如 QK/PV 收缩、逐元素、归约；按 workload 中有意义的规模/布局分组，不要求硬凑小中大三组。记录各组几何、覆盖依据和拟用路线。只允许由通用几何/平台条件分流，不能按 case ID 或数据值记忆答案。

有主要矩阵收缩时，核查获准的官方矩阵 API、通用组件/模板与自定义实现的适用性，留下以下信息：

| 运算/路线 | shape、dtype、layout、平台支持域 | 精度模式与累加/中间类型 | workspace/适配与完整路径成本 | 支持证据、未知项、采用/否决理由 |
|---|---|---|---|---|

支持证据可为实际 SDK 头文件、官方文档、获准模板的版本与具体位置；区分“签名存在”“支持域已核对”“已运行精度通过”。严格 FP32 不等于只能用 Vector，也不能从 float 接口直接推断真实算术或精度合格。需验证项记 unknown 并安排区分方法，不能凭实现复杂就宣称不可用。不要求实际实现/计时所有备选路线。

`route_options[].primitive` 使用唯一名称，几何组的 `selected_route` 必须引用其中一项；组合/分流路线可作为一项说明其组件和条件。已确认 unsupported 的路线只能作为被否决备选，不能选用；选中 unknown 时填写 `support_finding_id`，关联具体支持域/精度未知问题、作者回应和独立处理结论。未选备选的未知不强迫整个设计放弃可行路线。

遵守盲测和资源范围：禁止读取的历史任务/其他实验臂仍不可读；允许的通用 SDK 组件可核查。纯 Vector、单 kernel、矩阵库串联、C/V 或规模分流均可选，没有固定赢家。没有矩阵收缩时写明不适用依据，不为凑字段引入矩阵路线。

## DESIGN 中的操作粒度成本表

每个几何组列主要阶段；不仅列 FLOPs、有效字节和峰值缓冲，还需下表。数量注明 global/per-block/per-task 范围、公式、核数/尾块/tiling 假设及来源，不能混用总量和单核量。

| 阶段/几何组 | 规约调用 | 标量UB读写 | 同步/依赖往返 | DMA调用数及每次粒度 | padding/尾块膨胀 | 输入重复读取 | FLOPs/字节/缓冲及依据 |
|---|---|---|---|---|---|---|---|

说明一个逻辑 tile 对应几次实际 DMA/向量/规约 API；已知范围可写公式，不伪造周期。片上数据也可能受小操作/标量往返限制；源码调用数不是指令数，重复源字节不是实测 HBM 流量，UB 放得下不证明流水有重叠。库内部未知项写 unknown，不要求反汇编库或猜造计数；不适用项说明理由。

矩阵主项若采用逐 score/key 的 scalar/GetValue/SetValue、短 ReduceSum、深度一小 DMA 等路径，独立走读应核查其随规模增长的成本，并与获准矩阵/批量路线比较。大例风险不能只用一句“性能未知，非正确性阻塞”带过；也不能为优化性能删除必要同步或放宽精度。

## 独立评审与交接

设计作者编写 DESIGN 与结构化记录；独立审查者阅读当前设计及支持证据，单列：

- `correctness_feasibility`：feasible / unknown / blocked（静态判断，不是精度PASS）。
- `performance_feasibility`：feasible / high_risk / unknown（静态判断，不是性能目标PASS）。
- `decision`：proceed / revise。未回应的问题必须 revise。高风险/未知项须保留 observation、设计者 response、验证计划及独立 reviewer rationale；审查者可依据明确的路线理由和区分计划接受风险，结论仍保持 high_risk/unknown。无需为常规设计取舍新增用户审批。

记录 author/reviewer 的实际角色身份及独立性；不同字符串不能证明独立性，协调者需核对真实派发记录，不用虚构角色补字段。风险接受不是让所有方案通过：作者须说明替代路线证据和为何保留当前选择，审查者可以要求改方案；不能仅填 PASS WITH NOTES、unknown 或“之后优化”闭合。

使用 [JSON模板](generation-design-review.template.json)（未填模板应检查失败），根据实际阶段填写分组/支持域/成本与问题。`artifacts` 绑定当前 DESIGN、外部合同、workload/manifest 及环境依据的路径和 SHA-256，路径相对记录文件；可增加实际 workload、精度标准等文件条目，合同本身已含精度/环境依据时可引用同一文件。外部合同无需新增内部结构约束。将 SDK/文档来源放入设计证据，脚本不联网核实它们。

顶层 `findings` 保存问题、作者回应及验证计划，`review.findings` 逐项给出 open/resolved/accepted_risk 与独立复核理由。作者完成后，用 `--assessment-digest` 获取除 `review` 外全部字段的规范化 JSON 哈希；该命令只算指纹，不作门禁判断。审查者核对当前内容后将指纹填入 `review.assessment_sha256`。变更路线、成本、问题回应或文件身份会使旧指纹失效，必须重新独立复核，不能只保留原 DESIGN 文件哈希。

```text
python <workflow-skill>/scripts/design_check.py --record <task>/docs/generation-design-review.json
```

主协调者在派发实现前核对原文并保存该命令的 stdout/退出码：0 且 `implementation_ready=true` 才可继续；2 表示字段/文件身份错误或需返回设计。脚本只核查结构、文件身份和风险闭合记录，不证明设计合理、角色真实独立或性能达标；它不挂钩/修改外部生成器，不会自动拦截绕过 workflow 的派发。`prepare generation` 可先用于下发设计，不能把 prepare 回执当本门禁。

开发若将已审批量操作改为逐 key 操作，或主要引擎/数据通路改变，先回报 design_issue；更新设计和哈希后由独立角色复审，不因“数学相同”跳过。将设计、结构化评审和回执随工程冻结，并作为 generation evidence 的 artifacts 归档；不增加修改不可变 run 身份的步骤。

## 保留首次正确冻结和真实验收

本检查不运行构建/NPU、不给速度、不计作已测正确或已测性能。设计核查、回应、修订计入原生成预算，不重置预算/修复次数；用户禁止冻结前性能搜索时不得启动探针或多路线 benchmark。有明确探针授权时沿用其范围与计费规则，不默认为全部任务增加上板。

第一次完整正确通过立即冻结 G，不为达标先换更快版本；性能未知先记 FIRST_CORRECT_FROZEN。固定10例、预热/重复、源码/库身份和原始测量审计保持不变；CLI generation result/decision 才据有效 R/G 决定交付或优化。性能不达标仍记 GENERATION_TARGET_UNMET，auto 可按原授权进入进化；固定 G 不随冠军替换。此记录的 proceed 不得作为 result 的 measured evidence。
