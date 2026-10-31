# 编写依据

2026-09-24：分发包以 Windows Codex 与 Linux Claude Code 为入口；本次实现验证使用项目指定的 gpt-6-sol / medium。主流程不硬编码模型，服从任务和项目调度规则。

- 已读取本机 skill-creator/SKILL.md：范围清楚、渐进读取、可重复逻辑用脚本、复杂技能独立前向测试。
- 已访问 [官方 Skills 文档](https://developers.openai.com/plugins/concepts/skills)：技能由SKILL.md与按需资源构成。
- 已访问 [GPT-6 model guidance](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6-sol)，正文确认Astra/Sol/Luna家族，并说明提示建议来自Astra行为、应在选定模型和workload上评估。本次保持用户指定Sol medium进行前向演练；没有把这些建议称为Sol专属实测结论。
- 2026-09-24 再核对[官方技能发现路径](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills)：Codex 项目技能使用 `.agents/skills`。Linux 入口依据 [Claude 子 agent 文档](https://code.claude.com/docs/en/sub-agents)与 [hooks 文档](https://code.claude.com/docs/en/hooks)，使用任务级 `.claude/agents` 和 settings。Codex 入口没有将 Claude hook 冒称为原生支持。
- 项目来源：算子开发对话复盘、CV 合同与交付记录、Vector 优化交接，以及本仓库 `op-case-generator` 的 MX 输入契约。历史私有运行材料不作为分发包可读取依赖。
- 目标来源为用户确定的工作流：首次生成默认相对原始基线1.2×；后续相对生成/复用起点1.5×；5轮每轮5候选；归档中间产物。生产、无运行演练和获准的执行启动核验分开。

本 skill 要求运行时解析真实 `ops-perf-evolution` 入口，不能因生成阶段 cwd 相同而把优化入口指向生成器目录。两个原始 init 的依赖及 hook 结构由集中初始化检查；兼容性以本次记录的来源哈希和验证结果为准。

## 2026-10-30：直接 AscendC 与受控生成对比

- 用户要求性能集固定10例、超大不超过3例，正确性仍全量；优化保留5小时有效执行、5轮每轮5变体，每轮结束先分析慢例/根因或可证伪假设，禁止单纯排列组合。
- 生成改用 `plugins-official/ops-direct-invoke` 的原始四角色及阶段模板，弃用 TileLang；安装依赖、合同和证据协议同步。CANNBot保持只读。
- 首次生成比较限定为 generation_only，两路全新隔离上下文、相同角色模型和原生生成器；每路2小时包含修复，首次全量正确立即冻结，再共同测性能。CLI新增可选冻结字段兼容历史run，不改写既有结果。

## 2026-10-08：C/V 串行分支

- 项目指定目标为 `gpt-6.1-sol` / medium；工作流继续服从实际任务的模型与并发配置，不强制修改调用者模型。Claude 入口未指定模型，未代选或声称完成某一 Claude 模型的实测。
- 本次读取本机 skill-creator，并重新核对 [OpenAI Skills](https://developers.openai.com/plugins/concepts/skills) 与 [GPT-6 提示指导](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6.1-sol)。后者的家族建议仍注明来自 Astra 行为，需在所选模型和 workload 上评估，不能称为 Sol 专属保证。
- 核对 [Claude Code skills](https://code.claude.com/docs/en/skills) 的按需参考文件机制，以及 [Claude 提示工程](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/overview) 的成功标准与评估原则。将串行模式放入单独 reference，主入口保留路由；未更改权限、hook 或启动参数。
- 分支依据项目 QLI 串行拆分、Compressor 成熟 C 替换与 packed/tiling 筛选、GMSQ 物理布局接入和 Vector 性能复盘。提炼完整流水复用、真实适配成本、全量/邻近 shape 验证、独立 oracle 与计时口径等可复用规则；私有对话、绝对路径和历史性能数值不作为安装依赖。
- 外部合同、内部边界与状态分别管理；优化接收完整组合 G，组件搜索共享父预算。此次验证为本地文档/归档/安装兼容及独立场景前向检查，具体结果见发行包 VALIDATION.md，不代表 NPU 性能达成。

## 2026-10-08：执行模式与监工协议

- 根据项目中 Vector、A5 C/V、L4 批跑和 GMSQ 的实际派发/纠偏记录，以及 QLI 用户明确切换 Codex 接管的记录，提炼可选择的执行分工，不把常用形式声明为普遍最优。
- 保留 Claude 在合同内连续执行、Codex 独立检查和纠偏；新增防重复派发、执行状态与验收状态分离、分阶段设备准入、失败候选终态收口、显式停止/接管等规则。周期监工服从当前任务授权，不从历史对话恢复定时任务。
- 沿用本日已核对的官方技能按需读取与评估原则；细则放入 execution-modes.md，主入口及双端初始化路由只指向规则。修改的是工作协议及生成的路由文字，没有新增自动派发/监控服务，也没有宣称真实双端任务已重新跑通。


## 2026-10-12：真实执行复盘与连续推进

- 使用当前项目首选 gpt-6.1-sol / medium 作为规范目标；本次模型不由skill硬编码。重新读取本机 skill-creator 及 [OpenAI Skills](https://developers.openai.com/plugins/concepts/skills)、[GPT-6模型指导](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6.1-sol)、[Claude Code skills](https://code.claude.com/docs/en/skills)。家族提示建议说明来自Astra行为，不能称为Sol专属实测；Claude框架不绑定实际API提供商。
- 依据实际GELU生成/进化、GMMSituQuant串行生成与监工纠偏，补充连续推进参考：完整任务必须从合格G实际进入进化；目标未达、故障、预算结束与用户暂停分开处理。新增scope为任务记录约定，没有新增CLI参数或后台调度服务。
- 提炼runner预检、独立golden/输入指纹、空case和正式计时规则；具体代理、设备、HBM阈值、CLI等待变量留在任务或环境记录，不固化为通用默认。此次修改不执行远端生成/搜索，不将历史实证计为新版本运行结果。

## 2026-10-30 默认按需进化修订

用户要求默认直接生成首版、先轻量验收、性能未达标再优化，保留固定10例/超大≤3/全量正确性/逐轮根因分析，并避免预先固定实现结构。本条覆盖前文历史记录中“完整任务必须实际进入进化”的默认要求；旧run及显式full范围不变。
