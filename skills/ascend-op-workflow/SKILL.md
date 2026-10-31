---
name: ascend-op-workflow
description: 将 AscendC、Triton 算子或 PyTorch 小算子组合串成可恢复的开发工作流：推导 shape、准备 workload、复用或生成 AscendC、进化优化并归档证据。默认 Codex 执行、Claude 可选；支持 MindIE 入口、完整开发及跨阶段续办。
---

# Ascend 算子开发工作流

接受源码路径/算子入口及已有配置、profiling、shape 材料。协调现有专业技能，不重新实现其 kernel 算法或评测器。使用前告诉用户本次进入哪个阶段；任务已有结论和授权直接沿用。

从 `/mindie-agent` 或 `$mindie-agent` 发起算子开发时，读取 [MindIE 接入与执行关联](references/mindie.md)，沿用当前宿主工具，不另建执行器。

workflow 和 CANNBot 是独立仓库。shape/workload 可独立使用；生成/优化需要完整 CANNBot 时，优先复用已知 checkout，缺少则询问是否安装或指定已有位置，选择安装后复用其原安装入口。拒绝安装时继续独立步骤并说明缺项。CANNBot 源码、脚本、模板与配置不修改，任务工程写入获准工作目录。

生成和多轮优化消耗较多 token，启动说明中简短提示，建议常规代码模型和中等 effort；复杂设计/关键正确性再按项目规则局部提升。默认 Codex 直接使用实际工具；Claude 仅在明确选择时初始化，不能把 Claude Agent/Hook 当作 Codex 原生能力。记录实际模型/effort，未知项如实标明，不填历史默认值。

## 默认目标与进入条件

- **默认路线 `auto`**：直接生成首版（或验证可复用实现）→轻量验收→按证据交付或优化。全量正确且固定10例性能达到合同目标时交付 G，优化记为 `NOT_NEEDED`；性能有效但未达标才实际进入已授权的 `ops-perf-evolution`。无有效测量不能认定达标，也不能用 prepare/HANDOFF 冒充完成。用户明确要求继续优化时使用 `full`，仅生成使用 `generation_only`；旧run沿用冻结范围。见 [连续推进与停止判定](references/continuation.md)。

- **R**：用户提供的原始实现，作为原始性能基线；正确性 oracle 单独命名和记录。
- **G**：进入优化前冻结的、全量正确的 AscendC 起点。没有对应且可复用的 AscendC 实现时先生成，默认目标 `GM(R_us/G_us) >= 1.2`。
- **O**：优化候选；默认 `GM(G_us/O_us) >= 1.5`，最多 **5 小时累计活跃时间、5 轮、每轮 5 个变体**，任一上限先到即停止。修复、构建、评测和分析计入预算，跨聊天不重置。G 不随冠军更新。5 个候选是搜索宽度，不代表必须同时启动5个Agent或占用5张卡。
- **评测集合**：正确性覆盖完整冻结 workload；性能预先固定为 **10个case，超大case不超过3个**。先按算量/逻辑存储规模定义超大阈值与选择依据，再生成候选；不得按已测成绩换例。`case_ids` 保留全量正确性含义，`performance_case_ids` 单列性能集合，两者均冻结。见[评测与逐轮分析](references/performance-and-round-review.md)。
- 输入是已有 AscendC 时，先核对接口/支持域与全量验证，合格后作为 G 跳过首次生成；输入是 Triton/PyTorch 时它通常是 R，除非已有匹配的 AscendC 候选可复用。
- 用户指定的基线、目标、轮数、精度和计量方式覆盖默认值。没有说明计时层级时，根据实际调用场景提出建议并在正式采样前明确；不暗用下游 skill 的默认分母。
- 同一 workload/计时条件下可另报 R/O；不能把历史 1.2× 与另一次 1.5× 相乘，声称已测得 1.8×。

## 实现路线

默认直接生成可运行首版，保留必要的语义、精度、资源和同步设计审查。实现来源（复用 / 模板适配 / 新生成）与结构分别决定；生成统一走**直接AscendC**，不调用TileLang设计、编译、调优或转译。首版前不强制 C/V 拆分、独立 pack/softmax/crop、多kernel或固定中间GM布局；由支持域、目标平台与成本证据选择。实现结构属于可修订设计，不是外部合同的不可变项。C/V拆分不强制重写已有组件。

生成入口为 CANNBot `plugins-official/ops-direct-invoke/AGENTS.md`。使用其真实角色与 `workflows/task-prompts.md` 对应模板，完成环境、DESIGN/PLAN、WALKTHROUGH、开发、审查、修复和验收。Codex原生角色可按项目模型/并发规则复用代理，记录角色兼任和独立性，不能把未实际执行的阶段记为通过。CANNBot源码与模板保持只读。

新生成或改变主要计算路线时，在实现前执行[生成设计评审](references/generation-design-review.md)：设计前核查获准组件的支持域与精度机制，设计中列实际操作粒度成本，独立走读分别判断正确性与性能可行性。主协调者读取设计及证据，运行 `scripts/design_check.py`；未闭合的风险退回设计。该静态门禁不替代实测，不要求多路线搜索或冻结前上板；禁止用“单kernel/UB可容纳”直接推断低时延。已验证且路线未变的完整复用工程沿用有效证据，旧run不追溯补写门禁。

仅在用户指定拆分，或已有证据支持评估独立 C/V 路线时，读取 [C→V 串行分支](references/cv-serial.md)。从 shape/workload 和外部合同出发，在首次生成前评估中间 GM 成本、检索成熟实现并筛选模板与 tiling；据此冻结内部接口。一项父任务管理 C/V 子任务，沿用完整 case、目标和总预算。完整实现可直接复用时，不为了走分支而拆分。

## 执行分工

标准分工：Codex负责需求、shape、workload、合同及实现选型与首次生成。建立G、进入进化、进化搜索三个阶段支持 **Codex＋Claude协作** 或 **Codex独立完成**，采用相同验收与预算。沿用用户已指定模式；无既定选择时由Codex独立完成，有明确Claude协作要求时才派发到已核实会话。恢复已有任务先核实原会话和活跃进程，不因规范更新抢占执行权。用户明确指定其他执行分工时以该任务要求为准。

需要协作时读取 [执行模式与监工协议](references/execution-modes.md)：Claude执行第5～7阶段的验证、修复与搜索，Codex管理冻结数据、交接和独立复核；Codex独立模式使用实际可用的工具/子agent，不需要启动Claude。当前执行者在合同和预算内连续推进。区分消息提交、接收、实际执行和验收通过；退出码/自报分数不替代原始证据。没有周期监控授权或可用调度能力时，不承诺后台看护。

## 生产与演练

默认 `production`。只有用户明确要求接线/占位演练时使用 `rehearsal`：允许模拟生成交接产物，禁止编译、NPU运行或写入正式通过状态；精度、性能均为 null/NOT_RUN。演练在优化准备阶段停止，不运行搜索/评测命令。演练产物必须与正式 dataset、run 隔离，见[接线演练](references/rehearsal.md)。

若用户进一步明确要求确认真实生成/优化agent及变异体能启动，按[执行启动核验](references/execution-smoke.md)建立独立执行测试。它可以使用真实已有实现打桩并做获准的最小验证，不能将旧rehearsal直接改成production或伪造基线成功。

## 阶段执行

0. **接收与定位**：读取输入源码和已有任务，确认算子范围、输入形式、真实外部 I/O、状态、目标环境、R及执行分工。绑定原执行会话或按授权准备新执行入口。扫描后仅询问材料无法解决的关键语义/业务决策。按需复用 `ascend-op-intake`；不因工作流新建而重复确认。
1. **shape推导**：使用 `operator-shape-derivation` 核对模型配置、执行轴、调用链和已提供 profiling。区分观测/推导/用户配置/假设。构造输入需要关联 metadata、state、量化布局时显式建模；不能只按 shape 去重。按覆盖需要使用 `op-case-generator`；case 数量不固定。详见[benchmark 接入](references/benchmark.md)。
2. **workload与可执行 benchmark**：准备 definition、workload、reference、inputs、manifest 和必要 runner；按目标仓库真实 schema/loader 验证，再部署到核实的 Level/独立 problem 目录。记录构造与 loader 证据；schema 通过不等于 NPU 正确。有状态算子提供同 S0 重置和完整输出/状态检查。
3. **外部合同冻结**：将接口、精度、全量正确性与10例性能集合、超大分类、计时、R/G身份、环境、预算和不可变项写入OPERATOR_CONTRACT；归档源码和输入哈希。新正式run自动强制固定10例与逐轮复盘；按合同传 `--optimization-seconds`（默认约定18000），用户预算优先；仅生成再加 `--stage-scope generation_only`。旧run不原地补写身份字段。仅选定 C/V 路线后冻结该修订的内部接口；不得把它预设为所有首版的约束。
4. **直接生成首版（按需复用）**：由Codex负责，按[生成设计评审](references/generation-design-review.md)完成路线核查、操作粒度成本表和独立性能可行性评审，再将已核对的设计记录及检查回执随任务交给开发者；不强制首版前进行多路线性能搜索。通过 `ops-direct-invoke` 生成缺失AscendC部分；C/V分支另完成[选型与边界冻结](references/cv-serial.md)。向真实生成角色传入工作副本、合同、完整正确性集合、固定10例性能集合和父目标；首个全量正确版本立即冻结G，随后按同协议测量性能并核对原始日志/库身份。设计记录纳入工程归档；结构或操作粒度实质偏离已审设计时先回报design_issue并复审，已冻结G则作为O对原G优化。本阶段的合格实测证据供第5阶段直接验收，不为切换阶段重复测量。用户要求与直接生成比较时，按[生成对照](references/generation-comparison.md)建立隔离且同条件的两路；不将准备prompt称作已生成。
5. **轻量验收与建立G**：轻量指先做一次完整的验收决策、不预先展开进化搜索，不减少全量精度、固定10例、预热/重复或源码/库身份检查。冻结首个全量正确版本，完成同协议 R/G 测量并记录 generation result；调用 CLI `decision` 读取已归档证据。`auto` 下达标交付 G，优化记 `NOT_NEEDED`；未达生成目标记录 `GENERATION_TARGET_UNMET` 并进入优化。没有正确性或有效性能证据时先修复/补测，不作达标推断。完整已有 AscendC 复用路线记 generation=SKIPPED_REUSED，验证不可跳过。新 C→V 组合需 C 独立、V 独立和组合验证；G 包括 C、V、边界、适配及统一 runner，不能用组件通过替代父任务通过。
6. **按需进入进化**：仅在 `auto` 验收性能未达标，或用户明确选择 `full` 持续优化时，按所选Codex＋Claude协作或Codex独立模式，读取并实际调用 `ops-perf-evolution` 的适用入口；显式传父任务剩余预算（默认最多5轮/每轮5候选）、固定G、目标（默认1.5×）和正式计时协议，核实接收及真实候选执行证据。

   新优化任务默认使用 adapter 的轻量路径：复用 `prepare optimization` 中 `baseline_acceptance` 指向的有效验收，只准备本轮候选；不为阶段切换重复构建/测量 G，也不预先铺开完整策略树、另一套 session/state/ledger 或 HTML。正式合同、G 身份、轮次与预算由父任务持续维护；用户选择的 `stage_scope=full` 只表示必须优化，不代表要求完整原生框架。恢复已有完整模式沿用原状态。lingxi 的正 engine_score 可低于 1，初始化、预约和反馈后的校验统一用 adapter 的显式 PyTorch 口径；原生校验结果单列，不能补 1 或改成相对 G。见[轻量交接](references/continuation.md#轻量优化交接)。
7. **进化搜索**：持续推进授权内轮次；C/V优化完整组合并共享预算。每轮结束先分析**每个候选**的慢例/退化项、证据、原因或可证伪假设，再归档 `round-review`；下一轮SELECT/派发前执行 `round-check`。没有足够证据可记unknown，但必须给出具体区分实验和预期观察。每个下一轮变体须关联本轮证据、明确机制改动和反证条件，不能只有参数组合。全部失败也形成有证据的分析终态。详见[评测与逐轮分析](references/performance-and-round-review.md)。下游相对PyTorch的score单列，正式G/O只按冻结性能集合；冠军替换仍需全量精度和同条件性能。
8. **收尾**：达标直交的 G 或最终 O 都须保持可复现；核对最终源码/路由/库对应的全量验收证据；身份未变且证据仍有效时复用已有验收，修改后补验受影响项并完成全量验收。输出逐 case R/G/O、总体加速比和退化项、原始采样及复现命令。报告优化为 NOT_NEEDED / NOT_RUN / 已执行及其结果；无可靠改善保留 G。结果区分精度通过/性能有效/生成目标/优化目标，以及原世界树校验和报告状态；归档通过不等于所有门禁通过。HTML 为可选展示，失败时保留错误并交付 Markdown、JSON 和原始证据，不修改 CANNBot 或伪造报告成功。预算结束允许交付 TARGET_UNMET。框架集成另列下一阶段；未实测不宣称整网收益。

## 资源、恢复和人参与

远端先遵循项目环境池及预检；不得继承示例机器、容器或设备号。复用指定现有 CANNBot/benchmark，不自动安装、改共享 skill 或重启容器。占卡规则采用本任务最新授权，不能泛化历史任务的50%阈值。只在明确授权时创建定时监控。

固定父任务身份，所有候选独立源码/build/log，恢复先读合同、state与checkpoint，再核实活跃进程，避免重复派发。路线或接口修订保留已用预算和旧证据，按[恢复协议](references/protocol.md)更新归档。资源门禁只阻止受影响的设备阶段，等待时仍可继续允许的代码/CPU工作；按候选终态收口，不等待失败候选永远不会生成的性能文件。5轮是上限；不要因失败清空计数重来，也不自动延长。

仅对影响业务语义、不可解配置冲突、扩大环境权限、增加预算或改变验收基线的事项请求人决定；给出证据与建议，暂停依赖该决定的工作，继续独立工作。普通编译/精度修复、合法 tiling 和候选否决在授权内自行推进。

## 文件入口与验证

主 skill 随任务记录实际依赖 skill 路径、版本、读取阶段；缺失时报告具体缺口，不把不存在的 `Skill()`/`Task()` 当真实工具。模型和并发遵循项目指令，本工作流不固定执行模型。

- [benchmark 接入](references/benchmark.md)：源码、shape、数据包和 loader 的衔接。
- [执行模式与监工协议](references/execution-modes.md)：Codex/Claude 分工、派发确认、诊断纠偏、资源等待及接管。
- [归档与证据协议](references/protocol.md)：目录、交接内容、目标分母与证据归属。
- [接线演练](references/rehearsal.md)：无 NPU 的独立前向测试与主协调者复核。
- [任务输入模板](references/task-template.md)：开始任务与阶段汇报时按需使用，不重复询问已知字段。
- [算子合同模板](references/operator-contract.md)：冻结接口、状态、精度、完整 case、计时和基线身份。
- [CLI与证据格式](scripts/CLI.md)：`workflow.py` 初始化、冻结、prepare交接、result验收及检查。CLI只在明确执行命令时生效，不是全局 hook。
- [编写依据](references/design-basis.md)：本项目来源、官方技能规范和模型指导核查范围。
