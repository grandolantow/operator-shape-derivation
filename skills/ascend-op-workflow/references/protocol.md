# 归档与阶段交接

使用独立 run；已有任务沿用目录并补文件地图，不强行迁移历史。推荐逻辑分区：sources、shapes、benchmark、contract、generation、optimization、evidence、delivery。具体由辅助脚本创建的目录以其 --help/输出为准；下游workspace可以是run子目录，通过相对路径或显式映射连接。

## 必须留存的证据

- 原始源码、输入材料位置与版本；允许读取的引用文件列入清单，不复制秘密信息。
- 工作负载及caseIDs、输入生成器、reference、正式合同冻结清单。
- 每次交接的发送内容、真实读取的skill入口与哈希、接收方确认、时间、前后阶段及下一步。
- 双端协作的执行身份、dispatch ID、接收与实际执行证据、监工观察/纠偏/落实记录；使用[执行协议](execution-modes.md)，不要把已提交当已执行。
- 生成工作副本、design、未完成假设、build/验证原始日志、源码与库哈希。
- 采用 C/V 分支时，保留实现选型记录、版本化边界、父/组件 case 映射和完整组合 runner；组件、组合证据分别归档。
- 优化起点G快照、每轮每候选的假设/路径/设备/验证/耗时/否决原因；保留冠军及失败方向。
- 最终报告、逐case绝对时间、原始样本、复现命令和限制。不能只有报告而没有支撑记录。

机器可读 evidence 描述的是具体执行的事实，至少包括：evidence_kind、candidate和baseline身份、workload身份、正式caseIDs、precision结果、measurement metric/protocol/run/device、原始结果路径和sha。不能仅由人为填写 `passed=true` 取代读取原始日志及现有 verifier。

## 目标与状态

生成目标：R/G ≥1.2。优化目标：固定G/O ≥1.5。GM默认对完整冻结case等权，若用户指定业务权重或逐case目标则以合同为准。报告退化比例和最差case；不合格/漏测case不能从分母删除。

lingxi等工具的内部相对PyTorch分数单列 `engine_score`。不要把内部target_speedup=1.5直接当成G/O=1.5；记录本轮adapter如何测量、聚合和决定停止。若无法控制内部早停，按剩余总预算恢复并记录，不能重置轮数或伪造达标。

G的全量正确性与性能有效，但R/G不足1.2时，可在原授权内交接优化，保留生成目标未达标。优化不得更换G为新冠军。已有AscendC复用路径G=validated_existing，首次生成目标不适用而非通过。

完整任务的 G 交接是阶段节点，下一步必须实际调用进化，不能据此关闭父任务。按[连续推进与停止判定](continuation.md)记录任务范围、真实执行证据和停止原因；阶段 TARGET_UNMET 不自动意味着父任务已完成。

任务报告状态采用事实：PREPARED、WAITING_INPUT、WAITING_RESOURCES、RUNNING、CORRECTNESS_FAILED、TARGET_UNMET、VERIFIED等。辅助脚本的 prepare 返回 preparation_id，只表示交接文件可用，不表示接收skill已执行；result 的实际状态为 REHEARSAL、TARGET_MET 或 TARGET_UNMET。任务阶段状态由协调者根据真实证据维护，不与CLI输出混称。生产完成还需主协调者复核原始记录。

执行状态与验收状态分开：记录执行端声明/证据以及协调者待复核/接受/返工结论。候选精度失败、超时或取消可形成带原因的终态，不要求它产生性能文件；资源等待仍是可恢复状态。只有验收证据符合合同才给父任务标记通过。监控、执行和执行者交接的停止/恢复分别记录。

## 演练隔离

所有演练交接标记 `mode=rehearsal` 与 synthetic。占位源码以显式异常阻止执行，不写看似可用的假kernel。无精度/性能测量时值为null，不能填写1.2/1.5作为实测结果。目标值可以存在，测量值不得存在。禁止把演练manifest直接提升为production；实际生成需新正式run重新验证。

## 恢复与变更

恢复指定run读取清单并重查哈希；先确认是否仍有执行进程，再派发。新的合同/输入修订或实现变动会使相关验证失效。只追加新交接、快照、记录，避免覆写前次成功/失败证据。设备等待和正常任务失败不是同一种终止条件。

## 父任务与 C/V 子任务

只维护一个父任务状态入口，已有看板/状态文件可继续使用并在文件地图中指定；新任务建议 `evidence/workflow_state.json`。最小字段为父任务 ID、当前合同/边界修订、实现路线、当前阶段、C/V/组合包及证据引用、三层正确性、性能有效性、目标状态、已用/剩余预算、子任务活动和下一步。该状态由协调者依据真实记录更新；`run.json` 是 CLI 的归档索引，不自动代表子 agent 状态。

双端执行时增加执行模式、当前owner/会话、最近dispatch和检查记录引用。父索引由协调者维护，执行器自己的state由执行器维护，通过路径和时间/hash连接；不并发覆盖同一个JSON。

父任务冻结完整 G，一份候选记录描述一套 C/V/适配/runner 组合。C/V 子任务共享正式 case、目标和优化预算；分别记录候选已提出、静态淘汰、已编译、已上板和全量验证，不能把候选登记数当实际 NPU 运行数。组件通过后回到父任务执行组合验收。

生成交接附选型和边界及每路允许改动范围；优化交接再附固定完整 G、统一评测入口、已否决方向及剩余预算。CLI 的 `freeze --package` 应归档包含这些内容或不可变引用的完整工程；`prepare` 不会自动搜集 C/V 子任务，也不自动转发资料，协调者仍需实际发送并确认接收。

若中途切换路线，保留父任务身份、有效证据和已用预算。CLI 的 production/rehearsal mode（不是执行分工 executor_mode）、input_kind/case_ids/targets/optimization_plan 或已固定 G 需要合法修订时，新建关联的归档 run，记录前序 run 与变更原因，不手改冻结索引。新 run 只承接父任务剩余预算，不恢复成新的5轮；仅接口/实现修订且冻结身份不变时沿用原 run 追加快照。历史结果继续归属原合同与组合。
