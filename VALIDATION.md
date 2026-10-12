# 本次整合验证

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
