# 本次整合验证

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
