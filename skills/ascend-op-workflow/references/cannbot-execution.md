# CANNBot 执行适配

从本 workflow 进入 Codex/MindIE 算子生成或优化时读取。适配脚本随 workflow 技能安装，无需单独安装 `cannbot-codex`、vendor 快照或 Claude。MindIE 原生工具负责真实远端作业、租约、取消与恢复。

## 路径与安装

`ADAPTER` 指当前已安装 workflow 的 `scripts/cannbot`。进入生成或优化阶段时，在实际执行环境运行解析器。`TASK_DIR` 是该环境中父任务已存在且可写的绝对路径。已运行的任务沿用原交接中的路径和版本。若父任务目录有安装清单，解析器读取其中的 `cannbot_root`。合同另有明确路径时，在下列命令末尾加 `--cannbot-root /path/to/checkout`，覆盖安装时选择。

```bash
ADAPTER=/path/to/task/.agents/skills/ascend-op-workflow/scripts/cannbot
TASK_DIR=/path/to/operator-task
python3 -B "$ADAPTER/resolve_source.py" --task-dir "$TASK_DIR"
```

默认从[官方 CANNBot 应用仓](https://gitcode.com/cann/cannbot)的 `master` 拉取到 `$TASK_DIR/.workflow-deps/cannbot`，按该应用提交的 gitlink 初始化 `vendor/cannbot-skills`。解析结果写在 `.workflow-deps/cannbot-source.json`。续办读取该记录并核对两个 commit，无需再次访问上游。安装 workflow、推导 shape 和准备 workload 时无需解析。环境不允许联网或缺少依赖时保留已完成阶段，报告出错的依赖，也可使用任务显式指定的 checkout。

| 入口 | 用途 |
| --- | --- |
| [resolve_source.py](../scripts/cannbot/resolve_source.py) | 解析官方主线或指定 checkout，记录应用和技能版本及入口 |
| [prepare_workspace.py](../scripts/cannbot/prepare_workspace.py) | 按需建立任务内可写资源和原生脚本相邻目录，不安装工具、不注册 Hook |
| [world_model_adapter.py](../scripts/cannbot/world_model_adapter.py) | 调用指定版本原生 validator，单列原生结果，兼容明确的正 PyTorch 分数低于 1 |
| [reserve_nodes.py](../scripts/cannbot/reserve_nodes.py) | 先持久化候选预约和 lane → node 映射，再允许派发 |
| [generator_gate.py](../scripts/cannbot/generator_gate.py) | 显式调用外部生成器文档/精度门禁，保存日志、源文件身份与全量覆盖证据 |

## 执行路线

- **新优化任务**：按[轻量执行](cannbot-lightweight.md)，复用 G 有效证据，只准备本轮候选。
- **显式 native 或已有原生 state/anchor**：按[完整执行兼容](cannbot-native.md)，沿用原状态、固定 G 与剩余预算；不重新初始化已运行的任务。

不因角色名要求特定执行器；模型、effort、并发和设备使用服从当前项目与任务授权。native 角色保留算法、实现和评估职责，适配负责实际工具映射。没有实现/测量证据时，prepare、预约和 fixture 测试均不能记为算子成功。

## 生成入口

- `layout=application` 时，读取 `generation_entry` 与应用仓的 `harness/workflow-orchestrator/SKILL.md`。若需初始化原生执行环境，在独立的生成工作区按插件 `QUICKSTART.md` 准备。Codex 的项目级入口如下，两个源路径取自解析结果。

  ```bash
  bash "$SOURCE_ROOT/plugins-official/ops-direct-invoke/init.sh" project codex \
    "$GENERATION_WORKDIR" --skills "$SKILLS_ROOT"
  ```

  显式传入 `skills_root` 保留已固定的子模块版本。用生成入口的模板引导选择只做直接 AscendC 开发和验收的模板，使用其公开 harness 按任务契约启动或续办。性能优化由本 workflow 在验收后按任务范围决定。把 workflow 已审的 DESIGN、合同和 case 交给原生任务，保留适用的独立走读、实现、审核和验收。设计需要实质调整时，回到 workflow 复审后再实现。
- `layout=legacy` 时，继续读取 `generation_entry` 指向的 AGENTS、角色和 `workflows/task-prompts.md`，沿原直调方式执行。续办已运行的旧任务时沿用已有证据与入口。

## 原生资源准备（按需）

优化从解析结果中的 `optimization_entry` 获取进化插件及角色。应用仓布局使用 `ascendc-ops-perf-evolution`，旧布局使用 `ops-perf-evolution`。只有需要可写策略/知识或 `.claude/skills` 相邻布局时才准备资源。`SKILLS_ROOT` 来自解析结果的 `skills_root`，`WORKDIR` 是独立的候选执行工作区。

```bash
python3 -B "$ADAPTER/prepare_workspace.py" --workspace "$WORKDIR" --cannbot-root "$SKILLS_ROOT"
source "$WORKDIR/.cannbot/env.sh"
WM="$CANNBOT_WM_SCRIPTS"
```

默认只复制 world-model、strategies、knowledge。需要额外技能时重复 `--skill NAME`，例如 `--skill tilelang2ascend-translator --skill ops-profiling --skill ops-evaluation`。模板从完整 checkout 定位，确有需要时只复制选中的模板到任务工程；不自动搬入整套 `workflows/templates/archive_tasks` 及其第三方源码。原始 checkout 不写入；资源来源及内容哈希保存在 `.cannbot/workspace.json`。只有 `status=prepared` 才能执行。中断复制可重试同一命令；已发布的可写资源保留，不被上游快照覆盖。上游资源变动或未知目录占位会报错，不静默切版本。原任务已有原生布局时继续使用原布局，无需强行转换。

PowerShell 使用同样的 Python 参数，并点入生成的 `.cannbot/env.ps1`。资源使用普通目录副本，不要求符号链接权限。`--skill` 只准备所选资源，不自动解析或安装全部运行依赖；按原脚本实际 import/路径补齐需要的资源。

## 正式验收与全量覆盖

直接 AscendC/native-entry 工程使用合同指定的正式 verifier、真实 loader 全量枚举、输出/状态检查和实际加载库 SHA256。下面的 `generator_gate` 白名单只支持原生 translator/designer 的已知验证脚本，不能代替任意 direct-invoke verifier；不能为方便而放开任意命令白名单。

使用旧版 translator verifier 的 lingxi 任务中，设 `CANNBOT_SOURCE_ROOT` 为旧版 checkout 路径。在 `shared/` 外冻结 `{ "scope":"full", "expected_cases":N, "files":{"model.py":"sha256", ...} }`：N 来自真实 loader，files 包含参考、所有输入和评测合同。运行示例：

```bash
VERIFIER="$CANNBOT_SOURCE_ROOT/plugins-community/tilelang2ascendc-ops-generator/skills/tilelang2ascend-translator/scripts/verification_ascendc.py"
python3 -B "$ADAPTER/generator_gate.py" run --cannbot-root "$CANNBOT_SOURCE_ROOT" --workspace "$LANE_RUN" --full-manifest "$FULL_MANIFEST" -- python3 "$VERIFIER" "$TASK_DIR"
python3 -B "$ADAPTER/generator_gate.py" check --cannbot-root "$CANNBOT_SOURCE_ROOT" --workspace "$LANE_RUN" --require-full
```

正式运行前须明确设备；shell evaluator 还须明确 SoC。正式精度之后、性能前和反馈前核对 check。该脚本记录退出码、原始日志 SHA、验证器及 Hook 身份、参考/输入/候选指纹和实际 `case[]` 连续数量。shell evaluator 实际转调的任务内 verifier 也必须与指定 checkout 一致，并绑定其哈希。它包含 `.asc` 源码指纹，但不自动发现进程实际加载的 `.so`；编译成功、加载库路径/SHA 及与源码对应关系仍须由正式 runner 和父验收核实。任一身份变化均不能直接沿用旧 PASS。文档/精度事件门禁仍可用 `--mode pre|post|skill-post` 及 stdin JSON 显式调用；只在实际执行相应开发/诊断步骤后登记，不虚构读文档或诊断事件。

## 依赖边界

本仓 Python 适配脚本使用 Python 3.10+ 标准库，默认获取源码时需要 Git 及 GitCode 访问权限。应用仓的直调 harness 还需按其安装说明检查 Node.js 和实际 provider。原生脚本及设备阶段仍需要实际 CANN、编译器、torch/torch-npu、Bash、profiling 等依赖。尤其检查正式 evaluator 的真实 import；若 `AscendPerformanceTest.py`、`evaluate.py` 或 deep-profiling 入口缺失，报告具体缺项，不把时间采样当作精度通过。安装成功只证明入口可用，不证明 NPU 环境或所有 CANNBot 分支已就绪。HTML、完整 PMU/仿真按需要执行，失败如实单列。
