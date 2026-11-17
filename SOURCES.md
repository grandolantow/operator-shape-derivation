# 来源与维护边界

本仓库从原operator-shape-derivation仓库演进，保留Git历史。shape原有未提交内容按原字节迁入skills/operator-shape-derivation；根SKILL.md与scripts/check_execution_contract.py仅作为旧安装兼容入口。

- skills/operator-shape-derivation：原仓库现有shape技能，是唯一维护源；不再从个人技能目录或CANNBot快照回拷。
- skills/ascend-op-workflow、安装/初始化/启动工具：从此前项目的工作流发行包迁入，已改为显式外部CANNBot依赖；以本仓提交和安装manifest中的内容哈希确定身份。
- CANNBot generation/evolution：外部checkout的plugins-official/ops-direct-invoke、plugins-community/ops-perf-evolution及ops/infra依赖。不将这些插件复制进本仓，不运行其独占入口的init.sh。
- skills/ascend-op-workflow/scripts/cannbot 及 references/cannbot-*.md：从原本地 Codex 适配包迁入的工作流自有胶水代码和说明，现以本仓为维护源。显式使用外部 checkout，不包含原 CANNBot 源码、Hook 或 vendor；运行时按需复制的可写资源属于任务目录，来源和哈希记入该任务。
- agent_ops_init.sh：保留原有Huawei版权说明的可选环境脚本，附原来源许可证LICENSES/CANN-2.0.txt；集中init不会调用它。其已知行为见docs/INSTALL.md。

本仓不存凭据、代理认证、机器私有配置、模型权重或真实任务大日志。环境记录和算子产物归属任务目录。

安装manifest分别记录工作流源码位置、外部CANNBot路径、实际skills/agents/hooks来源与哈希。同名技能内容冲突时报错，不静默覆盖。

## Shape tiling 增量知识来源

- 本次维护范围：设计入口、原 DESIGN 的参数映射和按需读取路由，以及 `references/tiling/` 下的实质知识增量。不复制未变的32份基础 Markdown、独立 eval、FlashAttention正文、实验CSV/报告、四臂协议或交接模板。
- 资源生命周期、运行期开销、Merge-row、Norm融合、Pooling等整理自 `ascendc-tiling-design` 增强快照 `experimental_REV5`（2026-11-05）；原快照及身份见[不可变来源目录](https://github.com/lanhongsheng/operator-shape-derivation/tree/2619c00f74997b7d4b23ae86a77529ddc5ff0416/skills/ascend-op-workflow/references/tiling-knowledge)。相关衍生资料保留适用的 [CANN Open Software License 2.0](LICENSES/CANN-2.0.txt)；正文保留来源范围和平台限定，不改许可为更宽松许可。
- 本仓接入直接 AscendC 流程，快照的通用 shape 选型与实现核对合并进一份短指南。elewise、AR全载/分段的修改只提取预算增量；with-index、sort的 API 限定合并入 API 卡，不复制其原算法正文。原入口的增强用本仓读取路由承接。
- 四份用户提供的推理笔记按下表蒸馏，未复制其图片或全文，未据此授予其他原材料的再分发许可。来源哈希识别输入，交付文件哈希由待审包清单记录；两者不可混用。

| 输入资料 | SHA256 | 本仓内容 |
|---|---|---|
| 大模型推理 Vector 算子 Tiling 选型指南.md | `dc4efff1a86c3476eb228dadd3f065125211248a2b52e7edb1c9c088a8c5bbc7` | [vector-recipes.md](skills/ascend-op-workflow/references/tiling/vector-recipes.md) |
| 推理算子tiling分类.md | `fbd57e6a9c6fb0f79070819863e2d19411bc70d8df5129a2d1f8d81461fc970b` | [inference-routes.md](skills/ascend-op-workflow/references/tiling/inference-routes.md) |
| cann_vector_tiling_research_20260929.md | `265698d77b8d3ddcf8fa6fe3e5deeb679afac5d9c9a8c68608c4cc481a868592` | [source-observations.md](skills/ascend-op-workflow/references/tiling/source-observations.md) |
| add_rms_norm 算子 tilingKey 划分与启示.md | `37b0ecc01808d87c27ce7961e4f1bbdf255aa6ebdd93b4faff14e727649b09bd` | [add-rmsnorm-keys.md](skills/ascend-op-workflow/references/tiling/add-rmsnorm-keys.md) |

基础依赖仍是任务固定的外部 CANNBot checkout，入口 `ops/ascendc-tiling-design/SKILL.md`，读取路径见[路由](skills/ascend-op-workflow/references/tiling-reading-routes.md)。已核参考目录版本 `affd5a88dd956022a598adf2f5ed9f3e26718d48`，不是强制升级要求；引用的旧快照只作版本化参考，目标 SDK/官方文档决定实际 API 支持。保留本仓已有 Vector performance-best-practices 路由。

历史实验单独保留在[归档](https://github.com/lanhongsheng/operator-shape-derivation/tree/2619c00f74997b7d4b23ae86a77529ddc5ff0416/docs/experiments)，不作为本 PR 的性能有效性证明；知识引用不证明历史作者曾读取，本次不补签过去阅读或验收状态。源码调研是观察线索，不是当前官方保证。
