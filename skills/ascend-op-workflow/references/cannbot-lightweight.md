# 轻量执行

默认用于新的有界优化任务，包括只验证一轮的任务。它复用 CANNBot 的实现、选择与反馈能力，不新建执行器；调度与验收由当前父协调者负责。已有原生完整模式的 run 继续按完整协议恢复。

## 交接与最小准备

读取父合同和 optimization prepare。`baseline_acceptance.result_paths` 相对父归档根，指向已归档的 G 验收记录；先由父 `verify`/`decision` 检查散列，再核对实际日志、源码/库、输入及协议身份。这些证据有效时，不为进入优化重复构建或测量 G。身份变化、证据过期/缺失或设备/协议改变时，补验并保留旧证据。G 包身份和父已用预算不变。复用记录不免除每个新候选的正式全量精度与性能采样；计算 engine_score 时参考和候选必须来自同一次测量，不能挪用 G 的旧 R 时间。

只准备本轮搜索宽度内有证据支持的候选，记录机制、父实现、预期受益 case 和反证。按需检索策略，不要求额外凑齐固定数量的策略/开放/workflow 方向。若使用原生 SELECT，节点模式须符合实际选择配额；返回的 `free_N` 是占位项，不能预约或派发。可由协调者直接选择已经持久化的合法候选，写出同样的 `selections.json` 数组（`parallel_index`、`node_id`）；不必为满足 SELECT 配额增加无关候选。

使用现有工具的实际绝对路径。只读调用已知 CANNBot 脚本时无需另复制整套 runtime；需要写策略/知识或工具相对目录依赖时，才用 `prepare_workspace.py` 建立任务副本。原生 Python 调用使用 `-B`，不在只读源码目录创建缓存。

在 run 中维护最小 `world_model.json`：沿用原 schema，root completed、score 为真实 G 分数、best_score 为真实当前最佳，待测节点 open/score:null。保留唯一 session 身份、evo_dir、op_name、requested_rounds/actual_rounds_completed；父任务可提供身份与轮次，不必运行会清零历史的原生 session init。没有父任务时在 run 的恢复记录中保存同等身份、冻结清单和累计预算。世界模型结构校验不证明分数来源，测量与全量门禁仍由协调者核查。

## 校验、预约与候选执行

下面 `ADAPTER` 指本 workflow 的 scripts/cannbot 目录，`WM` 指已核实版本的 CANNBot evolution-world-model/scripts。lingxi 明确用 pytorch；ops 或未知分母用 native，不做该兼容。

```bash
python3 -B "$ADAPTER/world_model_adapter.py" --wm-scripts "$WM" --path "$EVO_DIR/world_model.json" --score-base pytorch
python3 -B "$ADAPTER/reserve_nodes.py" --wm-scripts "$WM" --wm-path "$EVO_DIR/world_model.json" --selections "$ROUND_DIR/selections.json" --parallel-map "$ROUND_DIR/parallel_map.json" --score-base pytorch
```

保存校验 JSON：`native_errors` 如实保留原生结果，`errors` 是 adapter 的接入判定。仅精确兼容已知 `best_score < 1` 错误；未知错误、非法状态、悬空父节点、会话错误仍阻断。非有限、非正数或布尔分数拒绝；不修改树内分数，不修改 native validator。原生 refine 有四位小数舍入，极小分数若变成零会被拒绝，不能用补 1 恢复。

预约脚本在预约前后使用同一判定，先排他创建恢复映射再提交树；成功返回后才允许候选执行。中断后若有映射而树未提交，先核对并完成原预约；不能删映射重新派发。只有一个协调者写树，脚本不提供多写者并发锁。

每 lane 使用独立源码/build/log/安装环境、冻结输入和正式 verifier。按[正式验收与全量覆盖](cannbot-execution.md#正式验收与全量覆盖)完成适用守卫/正式 verifier 后才采样固定性能集合；源代码、实际加载库与原始数据关联。当前任务的模型/并发/设备锁优先；无需为了不同角色新开 agent。

## 反馈与收尾

所有候选终态后，先核对实际源码差异、构建日志、实际加载库、正式精度/覆盖及真实性能，再调用原生 refine；具体参数见 [完整协议步骤 6](cannbot-native.md#初始化预约反馈的准确顺序)。不把 refine 当精度或测量执行器。每次 refine 后再次调用上面的 adapter 校验，不能回到原生的分数下限校验。

原生 artifact checker 仅识别其规定目录中的 `.cpp/.h`；对该布局读取 JSON 中逐 lane 的 fail/issues，不以退出 0 认定通过。`.asc` 或 native-entry 等布局由协调者复用正式 verifier、全量守卫与父验收证据，逐项检查真实源码变化、编译成功、实际加载库及源码/库 SHA256；将检查和原始证据一起归档。本 workflow 的 gate 已包含 `.asc` 源码指纹；实际加载库仍须显式记录路径/SHA，不能据源码指纹推断库已对应。原生 checker 的适用性单列 NOT_APPLICABLE，已运行的原始失败仍保留；不伪造 `.cpp`、不把真实缺源码/库/精度/采样忽略为布局差异。缺项候选不能晋级。

轻量模式不要求单独初始化/验收 ledger；原生 refine CLI 自动产生的 ledger 等附带产物仍留在本 run，不代表另一次执行或验收通过。

完整 PMU、仿真按具体瓶颈需要采集；仅时间数据时 pipeline=null，原因可标为待证假设，不声称硬件利用率或完整流水闭环。每轮仍在父任务归档 round-review，下一轮实际 SELECT/派发前 round-check；用户一轮上限到达后不再准备下一轮。

正式优化验收只按固定 G/O、全量精度及父合同；内部 PyTorch/候选 score 单列，不单独触发父任务达标或换 G。Markdown/JSON 与原始证据足以交付；原生 HTML、独立 ledger、session/state 报告在父任务已承担相同职责时不重复要求，也不标成原生检查 PASS。未运行项记 NOT_REQUESTED/NOT_RUN。没有更优正确候选保留 G，最终复核可复用身份未变的有效证据。
