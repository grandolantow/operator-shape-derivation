# operator-shape-derivation

面向算子开发和性能测试的 Codex skill。根据目标算子、模型与运行配置、源码及可选 profiling，推导输入、输出和中间张量 shape，并生成可重跑的 workload 配套产物。

支持已有单算子，以及由 A、B 等组成目标算子 C 的需求。先分析调用链和数据流，仅在存在影响 shape 的歧义时询问用户。完整行为以 [SKILL.md](SKILL.md) 为准。

## 输入与交付

提供目标算子及可定位的源码或接口材料；模型配置和运行参数按目标需要提供。已有材料能够确定的信息由代理自行提取。

Profiling 优先索取，用户明确没有后再采用明确标注的场景假设。已经指定的具体测试参数可以同步推导和导出，不冒称真实运行分布。

默认交付推导说明、结构化 shape、可重跑脚本、npu-kernelbench workload 和必要的输入生成器。指定其他 benchmark 时读取其实际 schema 后适配。definition/reference 缺失时列明接入缺口。

普通输入可由框架内置描述符生成；关联 metadata、特殊 stride/别名及可写 state 等需要专门的构造逻辑。当前版本也要求在普通描述符足够时提供简洁的构造或验证入口，具体见 [workload 交付](references/workload-delivery.md)。

## 安装

Skill 安装只需要完整的技能目录。运行 Codex 的环境需要能读取该目录；执行本技能的推导脚本和检查器时需要 Python 3。新增检查器只用 Python 标准库，无需安装 Conda、Zhanlu 或 PyYAML。实际构造张量/运行 benchmark 时，再使用目标工程所需的依赖。

### Linux 服务器

使用实际运行 Codex CLI 的 Linux 用户执行；首次安装时目标目录应不存在：

```bash
mkdir -p ~/.agents/skills
git clone https://github.com/grandolantow/operator-shape-derivation.git \
  ~/.agents/skills/operator-shape-derivation
```

`~/.agents/skills` 是当前官方文档列出的用户级搜索路径，适用于该用户的多个项目。安装后在 Codex 中输入 `/skills` 查找，或直接使用 `$operator-shape-derivation`。Codex 会自动发现技能变化；没有出现时重启 Codex。来源：[官方技能搜索路径与使用说明](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills)（核对日期：2026-09-11）。

### Windows

首次安装也可直接克隆到用户级目录：

```powershell
$skillInstallRoot = Join-Path $env:USERPROFILE '.agents\skills'
New-Item -ItemType Directory -Force -Path $skillInstallRoot | Out-Null
git clone https://github.com/grandolantow/operator-shape-derivation.git (Join-Path $skillInstallRoot 'operator-shape-derivation')
```

### 容器、项目级安装与离线复制

- Codex 在容器内运行时，安装到容器内运行用户的 `~/.agents/skills`，或容器可访问的项目级目录。安装位置取决于 Codex 在哪里运行；仅算子测试在容器内时，不必因此再安装一份。
- 只给某个项目使用时，在该项目根目录创建 `.agents/skills`，把仓库克隆或完整技能文件夹复制到 `.agents/skills/operator-shape-derivation`。然后从该项目启动 Codex。
- 服务器无法访问 GitHub 时，传输完整的 `operator-shape-derivation` 目录，保留 `SKILL.md`、`references/`、`scripts/` 和 `agents/` 等内容。开发验证产生的临时依赖、快照和报告不是安装依赖。
- 本地尚未推送的修订不会出现在 GitHub 克隆结果中；分发这类修订时，先提交并推送，或直接传输对应本地文件版本。

### 更新与开发目录链接

通过 Git 克隆安装的用户，后续在没有未处理本地改动时更新：

```bash
git -C ~/.agents/skills/operator-shape-derivation pull --ff-only
```

Windows 对应：

```powershell
git -C (Join-Path $env:USERPROFILE '.agents\skills\operator-shape-derivation') pull --ff-only
```

普通安装不需要链接目录。如果希望在其他开发目录维护仓库，可将用户级技能目录链接到该仓库；Codex 支持符号链接。Windows 可在克隆后的仓库根目录执行以下命令，目标入口必须不存在：

```powershell
$skillInstallRoot = Join-Path $env:USERPROFILE '.agents\skills'
New-Item -ItemType Directory -Force -Path $skillInstallRoot | Out-Null
New-Item -ItemType Junction -Path (Join-Path $skillInstallRoot 'operator-shape-derivation') -Target (Get-Location).Path
```

已有环境若通过旧目录或自定义入口加载此技能，可保留已确认可用的入口；这份 README 不会迁移安装。避免同时保留多份同名技能而混淆生效版本。

## 使用

~~~text
$operator-shape-derivation

根据这里的 A、B 算子和调用代码，设计组合算子 C 的 shape。
源码和模型配置在指定目录，运行配置和 profiling 路径随任务提供。
生成 npu-kernelbench workload 和必要的输入生成器。
~~~

没有 profiling 时明确说明，并给出已知配置、测试范围或具体用例。shape 数据需要分别标明观测、推导、假设和未知字段。

## 文件

- [SKILL.md](SKILL.md)：skill 入口、默认流程与交付范围。
- [证据与 shape 推导](references/evidence-and-shapes.md)：组合接口、容量/有效工作量、dtype/layout/stride 与证据规则。
- [workload 交付](references/workload-delivery.md)：产物结构、benchmark 适配和输入生成语义。
- [推导案例](references/examples.md)：组合算子与 Compressor 的方法示例；具体公式不作为通用默认。
- [执行量门禁](scripts/check_execution_contract.py)：检查目标相关执行量的范围、未知/假设依赖和人工判决状态；不验证业务公式。
- [agents/openai.yaml](agents/openai.yaml)：界面元数据。

## 验证范围

首次整理时已完成 skill 格式、引用链接和界面元数据检查，并用三个组合算子用例验证了 shape/workload 对应关系、确定性重生成和实际 npu-kernelbench schema。另行检查了 profiling 未提供时的行为。

这些检查不代表实际张量构造、算子正确性或 NPU 性能验证；原验证环境没有 PyTorch。使用本 skill 生成的新算子用例仍需按对应接口与框架重新验证。


2026-09-11 定向修订：执行量语义与人工判决、规则证据与预期关系检查分离。维护目标为 GPT-6 Astra，核对 [官方模型指导](https://developers.openai.com/api/docs/guides/latest-model) 与 [官方技能编写指导](https://learn.chatgpt.com/docs/build-skills)；采用窄范围约束和有意义的行为验证，不以格式检查代替正确性。具体首轮验证结果由本次修订验证报告记录。

本轮定向验证：16个GLM配置的四类投影得到64条规格，主线程独立核验192个tensor shape一致；11个边界case与原测试接口一致；歧义场景即时请求人工判决并停止相关导出。首版门禁的重复判决提示在复核中修复，最终11项回归测试通过。这不代表原731条workload或全模型/NPU重新验收。
