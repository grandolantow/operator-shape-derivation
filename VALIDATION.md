# 本次整合验证

## 2026-10-31：workflow 内置可迁移适配

- 将四个自有适配脚本及轻量/native 执行说明纳入 `ascend-op-workflow`，递归随技能安装并计入安装哈希。运行时显式指定外部 CANNBot checkout；无需独立 adapter 包、vendor 或宿主特定 Hook，MindIE-agent 原生作业工具保持现状。MindIE-agent 和 CANNBot 源码均未修改。
- 新任务目录使用普通目录副本准备所需原生资源，记录来源与哈希；中断可重试、恢复保留已有可写资源，上游变动或未知占位拒绝覆盖。只准备所选技能，不搬入整套历史模板或第三方源码；实际安装检查覆盖含空格路径及无需 Windows 符号链接权限的入口。
- Windows 根测试 65 项：60 通过、5 项既有符号链接/路径限制跳过；workflow 与设计检查 61 项通过，shape 合同 11 项通过，共 132 项通过、5 项跳过。根测试显式设置 `CANNBOT_SOURCE_ROOT`，其中 29 项集成测试使用真实 checkout `bcb8067bd6ebab19e490b317ad8250e25a18316b` 的 validator、select/refine 及生成门禁，未修改其实现。
- 从全新隔离任务的实际安装产物执行资源准备、正 PyTorch 分数低于 1 的原生校验兼容及候选预约，均通过；分数保持原值，原生错误单列。CANNBot 4705 个已跟踪文件按任务开始时的实际字节哈希复核，零变化，包括原本已有的本地修改。
- 门禁回归覆盖 `.asc` 修改、验证器及间接 verifier/Hook 身份变化、原始日志和输入清单变更、全量计数缺失、非法分数和预约重入。独立审查通过；skill 结构、Python 语法、Markdown 相对链接及 `git diff --check` 通过。

边界：这是离线安装、原生脚本接线及证据检查验证，不包含新远端作业、NPU 构建、精度或性能实验。fixture 的候选结果不代表实测。直接调用工程仍使用合同中的正式 verifier；实际加载库及其与源码的对应关系仍需正式 runner/父验收核实。适配器不安装 CANN、torch-npu 或外部 evaluator 的运行依赖，也不承诺任意版本 CANNBot 接口均兼容。

## 2026-10-31：实现前设计评审与PR回归

- 新生成或主要计算路线变更时，增加获准组件支持域核查、操作粒度成本表及独立的正确性/性能可行性评审。保留首次全量正确立即冻结G、固定10例实测验收与原预算；不修改CANNBot，不给历史run补写身份字段。
- 新增标准库只读 `design_check.py`：绑定DESIGN、合同、workload与环境依据的文件哈希，以及作者全部评估内容的摘要；拒绝未声明或unsupported的选中路线、缺失回应、开放问题、陈旧评审。未知或高风险保留原标签，仅在有具体验证计划及独立处理结论时允许继续。未填写模板与仅计算摘要均不产生实施许可。
- Windows完整回归：根测试31项（26通过、5项因Linux符号链接/路径语义跳过），workflow与设计检查58项通过，shape执行合同11项通过；共95项通过、5项跳过。设计检查21项涵盖文件/路线/成本/回应变更、风险闭合及失败分支。
- 独立审查发现并修复两项归档一致性问题：逐轮门禁从冻结回执核对轮次、顺序和停止标记；不同固定G的generation result在写入前拒绝。新增回归验证索引漂移不能派发、失败写入不改变归档，以及无顺序回执的旧归档仍可读取但不自动续跑。修复后独立复核通过。
- workflow技能结构校验通过，校验依赖安装在任务隔离目录；没有全局安装或配置修改。GitHub CI状态以实际PR结果为准。

边界：本次回归验证本地控制逻辑、安装计划和证据结构，未新增NPU或远端实验，不能据此宣称新门禁已改善算子性能。脚本不验证角色实际独立性、SDK文档真伪、成本模型或原始性能数据真实性；主协调者仍需读取证据并执行实测验收。

## 2026-10-30：默认直接首版、轻量验收与按需优化

- 新run默认stage_scope=auto：先直接生成/复用首版，实测R/G验收后，达标交付G；未达标才允许优化。decision重新核查冻结证据，不信任可修改的索引状态；缺失、演练或冲突测量不能推断达标。显式full覆盖是否必须优化；旧run缺字段时保持历史语义。
- 所有新production范围强制固定10个性能case、超大最多3个，以及逐轮分析；全量正确性不缩减。auto的AscendC复用同样需要measured验收。固定G和阶段证据绑定受检查，恢复不会换分母。
- 主skill、连续推进/验收/合同模板、Codex及Claude安装路由同步更新。不预设首版kernel数量、C/V拆分或中间GM布局；逐轮分析同时检查实现瓶颈与搜索策略，要求控制变量及可证伪的下一步实验。已有有效首版验收证据可复用，不因切换阶段重复测量。
- Windows workflow单元测试34/34通过；根测试31项，26通过、5项平台相关检查跳过。安装测试核对两类生成路由均包含新策略。git diff --check与本地Markdown相对链接检查通过。
- 当前安装目录为指向本仓的Junction，已核对实际目标；修改对该本地skill入口生效，无需重新复制。其他任务的独立安装副本未批量更新。

边界：本次验证流程控制、归档证据检查与安装产物文本；未启动远端、NPU、生成或优化任务，未重新测量算子性能。CLI不证明原始profile的真实性，也不自动执行派发、墙钟预算或业务退化阈值；这些仍由协调者按合同核查。

## 2026-10-30：直接 AscendC 生成与固定10例测量

- 生成入口改为原生 `plugins-official/ops-direct-invoke`，保留其设计、独立走读、逐步编译、独立代码审查和精度验收；安装器不再引入 TileLang 设计/转译依赖。真实源预览为27个skills、Claude模式8个agent声明；本次实际执行使用Codex角色，没有调用Claude API。
- workflow测试23项全部通过（Windows与Linux）；根测试集31项，Windows跳过5项平台相关检查。skill-creator结构校验在已有PyYAML的Linux环境通过，未安装全局依赖；相对链接与`git diff --check`检查通过。
- 新manifest分别冻结完整正确性与恰好10例性能集、所有正确性case的规模分类；超大性能case最多3例。新增逐轮分析/下一轮门禁、18000秒预算字段和`generation_only`保护。旧run保留原语义，不补写历史身份字段。
- 在同一Ascend910_9382 / DAV_2201、CANN9.1、Torch/Torch-NPU2.10环境完成全新SDPA对照：A使用workflow，B从原生生成入口进入。两路声明相同角色模型/effort，首次全29正确后立即冻结源与库；冻结包迁移加载再验29例全部通过。支持域为BF16 12例、FP32 17例，未将其声称为原始50例或FP16验证。
- A首次完整正确3808.017秒，B为3149.129秒；两路均低于各7200秒上限。A记录ABI调用桥接和交付脚本两轮修复，B为零轮；失败构建、独立诊断及原始回执保留，不重置预算。
- 固定性能10例（其中3例超大），同卡串行交错R/A/B采样，每路三次独立采样，逐例取pass均值的中位数。GM设备任务耗时为R 77.756μs、A 173.493μs、B 160.094μs；GM(R/A)=0.448176、GM(R/B)=0.485686，GM(B/A)=0.922769。两路生成性能目标1.2倍均未达成，未执行后续进化。
- 原始CSV审计发现B的tiling H2D使用`MEMCPY_ASYNC`，旧白名单拒绝；新版只补齐该任务识别，仍按原定正非metadata设备任务口径计入。R05/A01/B01使用原CSV重新审计，R/A耗时完全不变；没有重采或选择较快结果。修正和失败日志另存版本，共享CANNBot源码未改。
- 两路production归档均校验通过（各2个package、1个prepare、1个result），结果均为`TARGET_UNMET`。A归档实际参与生成编排；B仅在生成/测量后补录证据。交付保留首次正确源码和库、完整正确性日志、9组正式原始CSV及审计、失败记录和SHA256清单。

边界：时长是计算stream上的正设备任务之和（含同步/搬运），不含host调度或端到端墙钟；未采PMU，不能给出硬件bound结论。共享卡在共同锁内检查空闲，没有外部独占租约。模型身份依据派发声明，运行时初始化日志、temperature、解码seed及总token不可观测。单个生成对照不能推断总体成功率，或将全部耗时差归因于workflow编排。未来优化仍为5小时、5轮、每轮5个变异体，本次未启动。

## 2026-10-28：默认 Codex 实跑与最小入口验收

- 103 上完成指定 SDPA 源码 → 新 workload → 新生成 G → 一轮一个候选 O → 最终复测 → 父归档。G/O 原始全 50 例精度及双流 24 项均通过，归档 verified=true（3 packages、2 preparations、2 results）。
- 固定 G/O=1.017841574×，目标 1.5× 未达；性能没有独占租约，只是临时测量。原世界树内部 R/O=0.5133，不能与 G/O 混用。
- 原世界树 validate 对 best_score<1 的限制导致失败；原 HTML 报告因 hw_params=null 失败。两项保留失败，不修改 CANNBot，不把归档通过当作全部门禁通过。
- 独立原生 Codex CLI 新会话通过字面 `$mindie-agent` 发现并实际读取 MindIE 0.1.9 入口、任务内 workflow、MindIE reference 和 manifest，识别 `cannbot_root` 为空后询问复用/安装/独立准备。拒绝安装后实际交付 torch.add 的合同、workload、shape 推导与标准库检查；生成/优化没有运行，benchmark loader 未提供，明确未验证。
- 103 Linux 根测试 28/28、workflow 测试 13/13 通过；两个 skill-creator quick_validate 检查通过，无全局依赖安装。Windows 上另补验低于原始基线的正确 G 仍可作为固定优化基线，13/13 通过。
- 两个独立 remote-dev CLI 进程重新连接同一正在运行的 CPU job，原 PID/start_ticks 不变；取消测试检查父子进程退出，同期另一作业仍活跃。所有测试作业最终清理。原 SDPA archive 的 show/inspect/verify 重新检查通过，记录文件哈希不变。

边界：新会话入口验证采用真实原生 Codex CLI，不是脚本文本检查，也不是桌面 UI 交互。Windows 默认 shell 曾因 CreateProcessWithLogonW 1385 失败，使用自动审批执行必要命令后通过；不改全局配置。当前桌面 MindIE remote-dev 仍报 release.update/harness_readback 路径检查错误，CPU 作业验证走已配置的环境池 remote-dev 0.10.7；不能宣称该插件故障已修复。未注入服务器/网络硬故障、未恢复进行中的长优化、未验证 coordinator 独占租约、Claude 实际 API 或多宿主。

详细事件日志、PR 草案和机器相关路径保存在工作区 dev_docs，不加入发布包。CANNBot checkout、Benchmark 和既有生成结果保持不变。只复验受影响范围，不重跑完整生成优化。

## 2026-10-12：独立仓整合

日期：2026-10-12。执行环境为 Windows；本次验证仓库组织、安装与旧接口兼容，不运行真实算子生成或设备计算。

| 检查 | 结果 |
|---|---|
| 根 tests：安装、启动包装和旧 shape 接口 | 26 项：20 通过、6 跳过 |
| shape 执行合同检查 | 11/11 通过 |
| workflow 冻结、基线、交接与证据校验 | 9/9 通过 |
| 外部 CANNBot 实际 checkout 的 Codex 安装 | 隔离任务目录实际安装 26 skills，重复 apply 成功 |
| 外部 CANNBot 实际 checkout 的 Claude 初始化预览 | 26 skills、5 agents，可生成安装计划 |
| 原 shape 文件迁移 | 原工作树的 8 个技能文件（含 README 和未提交修订）按 SHA256 对照保留 |
| 旧 checker CLI 与导入 | 正常、未决、错误退出码及 JSON、validate_contract 导入兼容 |
| Git whitespace | diff --check 通过，Windows 换行提示不影响检查 |

6 个跳过项需要 Linux 符号链接和反斜杠文件名语义，未将 Windows 的跳过当作 Linux 实测通过。启动包装使用模拟 Claude 校验参数；没有实际调用 Claude API。没有编译、NPU 精度或性能结果。本次迁移不重启既有远端任务。

skill-creator 的 quick_validate.py 未运行成功：本机两个现有 Python 均缺少 PyYAML，未为此安装依赖。入口与相对链接另行检查；这不等同于该验证器通过。

复现命令见根 README。测试 fixture 中外部 CANNBot 不含工作流 tools 目录，验证安装器从本仓读取工作流与 shape，从外部 checkout 读取生成和进化依赖。
