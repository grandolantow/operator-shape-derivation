# 来源与维护边界

本仓库从原operator-shape-derivation仓库演进，保留Git历史。shape原有未提交内容按原字节迁入skills/operator-shape-derivation；根SKILL.md与scripts/check_execution_contract.py仅作为旧安装兼容入口。

- skills/operator-shape-derivation：原仓库现有shape技能，是唯一维护源；不再从个人技能目录或CANNBot快照回拷。
- skills/ascend-op-workflow、安装/初始化/启动工具：从此前项目的工作流发行包迁入，已改为显式外部CANNBot依赖；以本仓提交和安装manifest中的内容哈希确定身份。
- CANNBot generation/evolution：外部checkout的plugins-official/ops-direct-invoke、plugins-community/ops-perf-evolution及ops/infra依赖。不将这些插件复制进本仓，不运行其独占入口的init.sh。
- skills/ascend-op-workflow/scripts/cannbot 及 references/cannbot-*.md：从原本地 Codex 适配包迁入的工作流自有胶水代码和说明，现以本仓为维护源。显式使用外部 checkout，不包含原 CANNBot 源码、Hook 或 vendor；运行时按需复制的可写资源属于任务目录，来源和哈希记入该任务。
- agent_ops_init.sh：保留原有Huawei版权说明的可选环境脚本，附原来源许可证LICENSES/CANN-2.0.txt；集中init不会调用它。其已知行为见docs/INSTALL.md。

本仓不存凭据、代理认证、机器私有配置、模型权重或真实任务大日志。环境记录和算子产物归属任务目录。

安装manifest分别记录工作流源码位置、外部CANNBot路径、实际skills/agents/hooks来源与哈希。同名技能内容冲突时报错，不静默覆盖。
