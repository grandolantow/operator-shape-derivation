# operator-shape-derivation

面向算子开发和性能测试的 Codex skill。根据目标算子、模型与运行配置、源码及可选 profiling，推导输入、输出和中间张量 shape，并生成可重跑的 workload 配套产物。

支持已有单算子，以及由 A、B 等组成目标算子 C 的需求。先分析调用链和数据流，仅在存在影响 shape 的歧义时询问用户。完整行为以 [SKILL.md](SKILL.md) 为准。

## 输入与交付

提供目标算子及可定位的源码或接口材料；模型配置和运行参数按目标需要提供。已有材料能够确定的信息由代理自行提取。

Profiling 优先索取，用户明确没有后再采用明确标注的场景假设。已经指定的具体测试参数可以同步推导和导出，不冒称真实运行分布。

默认交付推导说明、结构化 shape、可重跑脚本、npu-kernelbench workload 和必要的输入生成器。指定其他 benchmark 时读取其实际 schema 后适配。definition/reference 缺失时列明接入缺口。

普通输入可由框架内置描述符生成；关联 metadata、特殊 stride/别名及可写 state 等需要专门的构造逻辑。当前版本也要求在普通描述符足够时提供简洁的构造或验证入口，具体见 [workload 交付](references/workload-delivery.md)。

## 安装

首次安装且目标目录不存在时，可直接克隆到个人 skills 目录：

~~~powershell
$skillsRoot = if ($env:CODEX_HOME) { Join-Path $env:CODEX_HOME 'skills' } else { Join-Path $env:USERPROFILE '.codex\skills' }
New-Item -ItemType Directory -Force -Path $skillsRoot | Out-Null
git clone https://github.com/grandolantow/operator-shape-derivation.git (Join-Path $skillsRoot 'operator-shape-derivation')
~~~

如果希望在开发目录中维护仓库，可在克隆后的仓库根目录执行以下命令，将个人 skill 入口链接到仓库。目标入口必须不存在；已有安装需先核对内容后迁移。

~~~powershell
$skillsRoot = if ($env:CODEX_HOME) { Join-Path $env:CODEX_HOME 'skills' } else { Join-Path $env:USERPROFILE '.codex\skills' }
New-Item -ItemType Directory -Force -Path $skillsRoot | Out-Null
New-Item -ItemType Junction -Path (Join-Path $skillsRoot 'operator-shape-derivation') -Target (Get-Location).Path
~~~

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
- [agents/openai.yaml](agents/openai.yaml)：界面元数据。

## 验证范围

首次整理时已完成 skill 格式、引用链接和界面元数据检查，并用三个组合算子用例验证了 shape/workload 对应关系、确定性重生成和实际 npu-kernelbench schema。另行检查了 profiling 未提供时的行为。

这些检查不代表实际张量构造、算子正确性或 NPU 性能验证；原验证环境没有 PyTorch。使用本 skill 生成的新算子用例仍需按对应接口与框架重新验证。
