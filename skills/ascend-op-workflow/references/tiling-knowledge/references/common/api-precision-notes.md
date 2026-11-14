# API 精度与语义注记（证据分级）

> **适用**：知识库中所有 API 行为/数值精度结论的引用方式。本文不新增 API 用法、
> 不复制任何手册内容；每条只记录：已知什么、证据级别、适用边界、如何升级证据。
> 生命周期与别名复用的物理口径见 [resource-lifetime.md](resource-lifetime.md)；
> 实现审查见 [shape 选型方法](shape-selection.md#设计与实现核对)。
>
> 本文沿用既有 API 审计中的证据分级与适用条件，具体结论不得跨目标版本或精度契约泛化。

---

## 一、证据分级（固定三档）

| 级别 | 含义 | 允许的用法 |
|------|------|-----------|
| `sdk-documented` | 目标版本 SDK/手册对**本平台**明确记载，且文中能指出来源位置 | 可作为设计依据；平台/版本变化后须重新核对 |
| `trial-observed` | 本轮受控对照试验观察到（须附任务/轮次标识、对照组设置、覆盖范围） | 只能作为本轮观察记录；不是普适规律，不迁移任务 |
| `hypothesis` | 以上两档都不支撑的推断，含"由一次失败反推出的根因" | 不得作为方案依据；只能列为待验证项 |

- 级别**逐条**标注：同一 API 在不同平台 / 编译器 / 优化级别 / dtype 上可以级别不同。
- 未标注的精度或 API 行为结论一律按 `hypothesis`（最弱档）处理。
- 本知识库当前**没有**任何 transcendental（Rsqrt/Sqrt/Exp/Reciprocal/…）精度数字
  达到 `sdk-documented`：不要从本仓库任何文件引用 ulp/误差数字。

## 二、逐条注记

### 2.1 同 dtype Cast 不等于拷贝（Claim A）

- **本仓库相关表述**：[../sort/patterns.md](../sort/patterns.md)（"若输入 dtype 为
  float32，则无需 Cast，UB 中可省去类型转换 buffer"）、
  [../sort/alg-two-level-mrgsort.md](../sort/alg-two-level-mrgsort.md)
  （"`Cast` API 要求独立的输出 buffer"）。
- **实际已知**：格式数学上，把已在 dtype D 中精确表示的值再 round 到 D 是恒等变换
  （可 CPU 复现）。但 Cast **API 指令**在 src/dst 同 dtype 时是否定义为透传、
  有何种别名/对齐/Buffer 约束、能否整体省略，是 API 行为问题，格式数学推不出来。
- **已核证反例（`sdk-documented` 级，20261023 补丁内对本机 SDK 头文件逐行复核，
  与独立审计存档一致）**：dav_c220（CANN 9.2.0 安装树
  `basic_api/dav_c220/kernel_operator_vec_vconv_impl.h`，float→float 重载起于
  508 行）的 `Cast<float,float>(..., CAST_NONE, ...)` 分支只有
  `DEBUG_ASSERT(false)` 后 break（提示文本在 545 行），**不含任何拷贝/转换
  指令**；同重载下 CAST_ODD 同样 assert。float→float 仅 RINT/FLOOR/CEIL/
  ROUND/TRUNC 五个模式对应五条 `vconv_f322f32*` 指令。`CAST_NONE = 0`
  （`kernel_utils_mode.h:95`）。即该平台该重载该 RoundMode 是**不支持的用法、
  不产出数据**，不是恒等拷贝。
- **同批否定的假设**："合法恒等 copy 被 O2 错误优化"已被 O0 控制流对照**否定**：
  O0 反汇编中 mode==0 直接跳到返回（偏移 0x1ec）；O0 里出现的 5 条 float→float
  VCONV 属通用 switch 的**其他** RoundMode 分支（RINT/FLOOR/CEIL/ROUND/TRUNC）。
  O2 折叠不可达分支是正常行为，不构成优化器缺陷证据。
- **证据级别**：dav_c220 float→float CAST_NONE 无拷贝：`sdk-documented`
  （SDK 源码 + O0 对照，附审计存档）；其他平台/重载/RoundMode 的行为：`hypothesis`。
  本节开头两处 sort 文档的无条件表述继续按 2.1/2.3 处理（未附出处）。
- **适用边界**：随 CANN 版本、SoC、**重载与 RoundMode 三元组**而变；一个三元组的
  结论不得推广到另一个。某轮任务"省去 Cast 后通过"只是该分支该版本的
  `trial-observed`，不推广。
- **升级方法（对照实验）**：先查目标版本 SDK 重载表确认行为，再上板：
  对照组 = 行为已定义的公式（显式 DataCopy 或确认有定义的重载）；
  处理组 = 待核证的同 dtype Cast。比较 bit 级输出与编译产物。
  反例一旦在 SDK 层确认（如 CAST_NONE），无需上板即可按不支持用法否决。

### 2.2 Rsqrt 等 transcendental 没有通用精度数字（Claim B）

- **本仓库相关表述**：
  [shape 选型方法](shape-selection.md)
  已有告诫（"近似数学API的误差需要按输入分布验证。不要根据某次Rsqrt问题给所有算子
  机械替换API。"）。两个 reference 树内没有 ulp 数字断言；仓库其余位置
  （plugin 技能资料）存在带具体数字的表述，属各自证据体系，本文不采信、不复制。
- **实际已知**：
  - 方法层面（CPU float32 可复现）：同一数学式的不同舍入方案
    （一步近似 `1/sqrt(x)`；`sqrt` 后 `Div`；再加一次数值精化）误差分布不同。
    所以任何精度数字必须绑定"具体 API/公式 + 中间 dtype + 舍入点"。
  - device transcendental 指令的逼近精度由硬件实现、编译器及其优化级别共同决定，
    CPU 无法代验。
  - SDK 层事实（`sdk-documented`，20261023 补丁内对本机 SDK 头文件复核）：
    dav_c220 的 Level2 `Rsqrt` wrapper 直接下发硬件 `vrsqrt`，无 SDK 内精化
    步骤，且仅支持 src/dst 同为 half/float（`kernel_operator_vec_unary_impl.h`
    Level2 `RsqrtImpl`，353-393 行）。
  - 试点差分（`trial-observed`，附轮次与受审源 hash）：RMSNorm validation-2 7/12 →
    validation-3 12/12，受审源唯一差异是在 `Rsqrt` 之后加一次牛顿精化（5 条
    单元素向量指令）——强差分证据支持"剩余误差可被 NR 步修复"。
  - **但裸 vrsqrt 的逐值硬件误差未被直接测量**：试点记录中的 ~2e-3 / ~2^-9
    相对误差是从最终 y 样本反推/拟合的**推断值**，不得当作硬件精度规格引用，
    也不得写成 per-instruction 测量；归约/均值舍入与端到端算术也未独立测量。
  - NR 精度的数学事实：若 `r0 = (1+e)/sqrt(a)`，一步 NR
    `r1 = r0*(1.5 - 0.5*a*r0*r0)` 后的精确相对误差为 `-1.5e^2 - 0.5e^3`
    （量级 e²、符号为负；写 `+e^2` 是错的）。
- **证据级别**："device Rsqrt 误差是 X ulp / X 相对误差"类命题：`hypothesis`
  （无直接测量；试点拟合值只能随试点引用）；"不同舍入方案误差不同"：格式/方法
  事实（CPU 可复现）；"SDK wrapper 无精化"：`sdk-documented`；"NR 修复了该试点
  剩余误差"：`trial-observed`（差分）。
- **适用边界**：平台 × 编译器 × 优化级别三要素任一变化都可能推翻结论；
  精度敏感路径不得引用记忆中的数字，也不得把一次替换的成功外推到其他算子。
- **升级方法（对照实验）**：目标环境固定 kernel 与冻结输入分布。
  对照组 = 已验证公式（如 Sqrt+Div 的 float32 组合或参考实现）；处理组 = Rsqrt。
  报告逐元素误差分布（不只 max），并改变编译优化级别重复，验证第三要素。
  满足该算子精度契约后才可把该公式标为 `trial-observed`（附任务标识）。

### 2.3 逐元素 API 的 in-place / 别名语义不设默认值（Claim C）

- **本仓库相关表述**：[../elewise/tiling.md](../elewise/tiling.md) 第六节把别名约束
  作为参数 K 由 API 层回填（此口径正确）；对照：
  [../sort/alg-two-level-mrgsort.md](../sort/alg-two-level-mrgsort.md) 存在
  无条件 Cast 独立 buffer 断言（见 2.1）。
- **实际已知**：两个 reference 树内没有"Mul 支持/不支持 in-place"的断言；正确立场是：
  任何逐元素 API 的 dst/src 别名能力都是 API 行为，逐平台、逐版本、逐 dtype
  组合待核证。账本必须按两种口径之一计算：保守假设不别名（独立 buffer），
  或引用已核证的别名结论。
- **证据级别**：任何具体"in-place 可行/不可行"结论：`hypothesis`，直至出现
  `sdk-documented` 条款或本平台受控对照。
- **适用边界**：别名"允许"≠数值安全——即使 API 接受 dst 与某 src 重叠，
  向量引擎段内读改写顺序仍可能使结果依实现而定；物理口径遵循
  [resource-lifetime.md](resource-lifetime.md) 的唯一写者与生命周期规则。
- **升级方法（对照实验）**：目标环境最小 kernel。对照组 = dst 与各 src 完全独立的
  物理 buffer；处理组 = dst 与某 src 同一物理 buffer（先同 dtype）。
  bit 级输出有任何差异即否决 in-place 写法；无差异也只升为该平台该版本的
  `trial-observed`，换 dtype/形状需重做。

### 2.4 一个 dtype 分支通过不排除共享上游原因（Claim D）

- **本仓库相关表述**：两个 reference 树内此前没有禁止这种推理的条文，本条新增；
  外部技能资料中存在按 dtype 分层下结论的写法，引用时同样受本条约束。
- **实际已知（20261023 shape-tiling v3 RMS 试点 `shape_tiling_v3_rms_pilot_01`
  及其独立审计观察，仅作观察记录）**：
  - RMSNorm：validation-1 6/12 → validation-2 7/12 的改动是**捆绑**的（同 dtype
    Cast 路径替换、FP32 输出计算、gamma 拷贝/y 写回/原位算术一起改），
    各单点因果贡献未在板上分离——不能把 6/12→7/12 归因于其中任何单一改动。
    validation-2 → validation-3 7/12→12/12 的受审源唯一差异是 NR 精化（见 2.2）。
  - RMSNormCast：validation-3 vs validation-4（移除 Mul 输出/输入别名）：库 hash
    变化但**保存的全部结果字段逐字节相同**——移除别名没有改变任何结果，
    "该 in-place Mul 是 fp16 失败根因"被这组差分**否定**（作为唯一解释）。
    validation-4 vs validation-5（CAST_ROUND→CAST_RINT）：部分输出与失配计数变化，
    但两轮均 13/24、同为 11 个 fp16 用例失败——舍入语义修正是必要修正但**不充分**。
  - bf16 全过**不是**上游数学的对照：评测器对 bf16 用 rtol=atol=0.02、对 fp16 用
    0.002，且中间舍入语义不同；容差与舍入都更宽的分支通过，不能排除两 dtype
    共享的上游问题；容差与舍入差异可能掩蔽同一误差来源。
  - **比较器短路**：冻结比较器在元组 output[0] 失败时立即返回，output[1]
    （如 inv_rms）即未被该次比较检验；"失败用例的 inv 已通过"没有记录支撑。
    分量 PASS 的断言必须指向实际执行并保存的比较结果。
- **证据级别**：以上通过率与"结果逐字节相同"的差分事实 `trial-observed`
  （附轮次/库 hash）；"别名/舍入/其他候选是根因"的解释 `hypothesis`
  （其中别名作为唯一解释已被 v3↔v4 差分否定；舍入修正被 v4↔v5 证明不充分）。
- **适用边界**：试点冻结的输入分布、shape 集、工具链与容差口径；不得迁移到其他
  算子/平台，也不得写成普适规律。
- **升级方法（对照实验）**：候选根因必须做成**单变量对照**（其余全部冻结，
  同一源双臂构建），在同一 fp16 输入分布上跑全量用例；仅当该对照改变通过数，
  "该变量是该 dtype 失败的原因"才升 `trial-observed`；"唯一根因"还需对其余
  候选变量逐一做排除性对照。

### 2.5 审计中发现的其他未限定表述

| 位置 | 表述 | 问题 | 处理 |
|---|---|---|---|
| [../broadcast/onedim.md](../broadcast/onedim.md) 故障表（"DataCopy 不支持非对齐"行） | 未附平台/粒度限定 | 对齐粒度是平台查询值（本仓 SKILL.md 已按此声明），写成无条件属性易被硬编码 | 保留行；结论按 `sdk-documented` 待目标版本核对后引用 |
| [../reduction/with-index.md](../reduction/with-index.md)（"aicore 中不支持 `static_cast<float>(uint32_t)`"行，已就地加注） | 无编译器/版本出处 | device 编译器行为随 CANN/编译器版本变 | `hypothesis` → 按目标工具链核证后升级 |
| [../elewise/patterns.md](../elewise/patterns.md)（"乘法/除法等其他场景暂未覆盖，沿用原 dtype 直算分支"行，已就地加注） | 路由缺口易被读成精度结论 | "未覆盖"是路由事实；"直算分支精度足够"没有证据 | 路由事实保留；精度充分性按 `hypothesis`，按本算子原精度验证确认 |
| [../reduction/ar-fullload.md](../reduction/ar-fullload.md) / [../reduction/ara-fullload.md](../reduction/ara-fullload.md) 故障表"FP16 精度差 / 中间计算精度不足" | 症状→根因未附定位证据 | 同一症状可由舍入、别名、同步、越界等多种原因产生 | 作为排查提示保留，根因表述按 `hypothesis` |

## 三、使用边界

- 根据目标 CANN、编译器和平台核对 API 语义；没有适用文档或设备证据时，明确为待验证假设。
- 精度公式、别名和升精度转换变化按原精度与全量验证流程确认，不能以另一 dtype 通过排除当前分支问题。
- 物理 buffer 唯一计数，只有真实同槽复用或重新初始化语义支持时才按阶段峰值记账；整数对齐运算先转宽再相加。
- 期望值和逐输出容差来自原算子规格；未执行的输出比较不得报告为通过。
- 本文只补充 API 与数值知识，不增加生成测试交付、图/跨流专项验收或新的运行接口。

## 四、相关知识

- [资源生命周期](resource-lifetime.md)
- [shape 选型方法](shape-selection.md)
- [逐元素 tiling](../elewise/tiling.md)
- [运行期开销](runtime-cost.md)
