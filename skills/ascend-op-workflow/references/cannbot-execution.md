# CANNBot 执行适配

从本 workflow 进入 Codex/MindIE 算子生成或优化时读取。适配脚本随 workflow 技能安装，无需单独安装 `cannbot-codex`、vendor 快照或 Claude。CANNBot 是显式指定的完整只读 checkout；MindIE 原生工具负责真实远端作业、租约、取消与恢复，本适配不新增执行器或后台服务。

## 路径与安装

`ADAPTER` 是当前已安装 `ascend-op-workflow/SKILL.md` 旁的 `scripts/cannbot`，不是本机历史目录。`CANNBOT_SOURCE_ROOT` 是当前执行环境中的 CANNBot checkout，从任务合同或安装 manifest 的 `cannbot_root` 获取；为空时沿用用户选定路径，不把本地路径带到远端。远端须同时能读取本 workflow 技能和该 checkout。以下 Bash 变量须替换为当前环境的真实绝对路径：

```bash
ADAPTER=/path/to/task/.agents/skills/ascend-op-workflow/scripts/cannbot
CANNBOT_SOURCE_ROOT=/path/to/cannbot-skills
export PYTHONDONTWRITEBYTECODE=1
```

安装器递归复制整个 workflow 技能并记录其内容哈希；不带 `--cannbot-root` 也会安装这四个脚本，shape/workload 仍可独立执行。带该参数时，外部技能快照仍是原始参考；优化执行以本入口和已选 profile 为准，不再另找同名 Codex adapter skill。

| 入口 | 用途 |
| --- | --- |
| [prepare_workspace.py](../scripts/cannbot/prepare_workspace.py) | 按需建立任务内可写资源和原生脚本相邻目录，不安装工具、不注册 Hook |
| [world_model_adapter.py](../scripts/cannbot/world_model_adapter.py) | 调用指定版本原生 validator，单列原生结果，兼容明确的正 PyTorch 分数低于 1 |
| [reserve_nodes.py](../scripts/cannbot/reserve_nodes.py) | 先持久化候选预约和 lane → node 映射，再允许派发 |
| [generator_gate.py](../scripts/cannbot/generator_gate.py) | 显式调用外部生成器文档/精度门禁，保存日志、源文件身份与全量覆盖证据 |

## 执行路线

- **生成**：继续直接读取外部 `plugins-official/ops-direct-invoke/AGENTS.md`、真实角色及 `workflows/task-prompts.md`。完成既有设计、走读、开发和审查，不进入 TileLang。Claude 的 Skill/Task/Read/Bash 语法由当前宿主真实工具承接；不假定自动 Hook 已执行。首个全量正确版本立即冻结 G，再实测。
- **新优化任务**：按[轻量执行](cannbot-lightweight.md)，复用 G 有效证据，只准备本轮候选。
- **显式 native 或已有原生 state/anchor**：按[完整执行兼容](cannbot-native.md)，沿用原状态、固定 G 与剩余预算；不重新初始化已运行的任务。

不因角色名要求特定执行器；模型、effort、并发和设备使用服从当前项目与任务授权。native 角色保留算法、实现和评估职责，适配负责实际工具映射。没有实现/测量证据时，prepare、预约和 fixture 测试均不能记为算子成功。

## 原生资源准备（按需）

只有原生脚本需要可写策略/知识或 `.claude/skills` 相邻布局时才运行：

```bash
python3 -B "$ADAPTER/prepare_workspace.py" --workspace "$WORKDIR" --cannbot-root "$CANNBOT_SOURCE_ROOT"
source "$WORKDIR/.cannbot/env.sh"
WM="$CANNBOT_SKILLS_DIR/evolution-world-model/scripts"
```

默认只复制 world-model、strategies、knowledge。需要额外技能时重复 `--skill NAME`，例如 `--skill tilelang2ascend-translator --skill ops-profiling --skill ops-evaluation`。模板从完整 checkout 定位，确有需要时只复制选中的模板到任务工程；不自动搬入整套 `workflows/templates/archive_tasks` 及其第三方源码。原始 checkout 不写入；资源来源及内容哈希保存在 `.cannbot/workspace.json`。只有 `status=prepared` 才能执行。中断复制可重试同一命令；已发布的可写资源保留，不被上游快照覆盖。上游资源变动或未知目录占位会报错，不静默切版本。原任务已有原生布局时继续使用原布局，无需强行转换。

PowerShell 使用同样的 Python 参数，并点入生成的 `.cannbot/env.ps1`。资源使用普通目录副本，不要求符号链接权限。`--skill` 只准备所选资源，不自动解析或安装全部运行依赖；按原脚本实际 import/路径补齐需要的资源。

## 正式验收与全量覆盖

直接 AscendC/native-entry 工程使用合同指定的正式 verifier、真实 loader 全量枚举、输出/状态检查和实际加载库 SHA256。下面的 `generator_gate` 白名单只支持原生 translator/designer 的已知验证脚本，不能代替任意 direct-invoke verifier；不能为方便而放开任意命令白名单。

lingxi 使用 translator verifier 时，在 `shared/` 外冻结 `{ "scope":"full", "expected_cases":N, "files":{"model.py":"sha256", ...} }`：N 来自真实 loader，files 包含参考、所有输入和评测合同。运行示例：

```bash
VERIFIER="$CANNBOT_SOURCE_ROOT/plugins-community/tilelang2ascendc-ops-generator/skills/tilelang2ascend-translator/scripts/verification_ascendc.py"
python3 -B "$ADAPTER/generator_gate.py" run --cannbot-root "$CANNBOT_SOURCE_ROOT" --workspace "$LANE_RUN" --full-manifest "$FULL_MANIFEST" -- python3 "$VERIFIER" "$TASK_DIR"
python3 -B "$ADAPTER/generator_gate.py" check --cannbot-root "$CANNBOT_SOURCE_ROOT" --workspace "$LANE_RUN" --require-full
```

正式运行前须明确设备；shell evaluator 还须明确 SoC。正式精度之后、性能前和反馈前核对 check。该脚本记录退出码、原始日志 SHA、验证器及 Hook 身份、参考/输入/候选指纹和实际 `case[]` 连续数量。shell evaluator 实际转调的任务内 verifier 也必须与指定 checkout 一致，并绑定其哈希。它包含 `.asc` 源码指纹，但不自动发现进程实际加载的 `.so`；编译成功、加载库路径/SHA 及与源码对应关系仍须由正式 runner 和父验收核实。任一身份变化均不能直接沿用旧 PASS。文档/精度事件门禁仍可用 `--mode pre|post|skill-post` 及 stdin JSON 显式调用；只在实际执行相应开发/诊断步骤后登记，不虚构读文档或诊断事件。

## 依赖边界

适配器本身仅使用 Python 3.10+ 标准库；原生脚本及设备阶段仍需要实际 CANN、编译器、torch/torch-npu、Bash、profiling 等依赖。尤其检查正式 evaluator 的真实 import；若 `AscendPerformanceTest.py`、`evaluate.py` 或 deep-profiling 入口缺失，报告具体缺项，不把时间采样当作精度通过。安装成功只证明入口可用，不证明 NPU 环境或所有 CANNBot 分支已就绪。HTML、完整 PMU/仿真按需要执行，失败如实单列。
