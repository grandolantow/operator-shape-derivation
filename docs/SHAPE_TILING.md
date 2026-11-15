# Shape 驱动 tiling：接入已有生成流程

## 改动落点

shape 推导回答“真实调用是什么形状”，tiling 分析回答“这个形状怎样分配核、tile、buffer 与数据依赖”。两者通过冻结的 workload 衔接，不把可观测形状清单误当完整 API 支持域。

原入口与设计评审 → 识别 shape/dtype/layout/语义 → 按知识路由读取正文 → 选择并解释 tiling → 原设计走读 → host/kernel 落实 → 原编译与精度 → 同版性能及逐 shape 分析。

本仓仍直接生成 AscendC，不新增 TileLang 路线。外部 CANNBot 简单/复杂路线不由该文重新划分。知识在原设计与审查位置使用；不新增自动读取监控、Hook 或必填 JSON。

## 三个选型例子

- 归一化：用独立行 M、归约长度 D、dtype 与峰值 buffer 判断整行驻留是否可行；短行多时再比较合行，D 放不下时比较核内分段与重读。Split-D 不自动增加独立任务数，不能仅为“铺满核”增加跨核同步。
- 插值/邻域读取：分析一组输出共享哪些输入行、权重与坐标；比较行/输出 tile 复用、重复 Gather、尾块和预处理成本。具体收益须来自同版精度及可比测量，知识本身不保证某个倍率。
- 直方图/索引冲突：先保持区间、重复索引及唯一写者语义，再比较输入分片后合并、输出分桶或排序；计入桶数放大的重扫、串行查找链、Gather 和同步。不能把“避免逐元素”理解成必须逐桶扫描。

## 如何确认知识被用到

在现有 DESIGN/PLAN 或评审中注明读了哪份相关资料、为何适用、采用的参数公式及未选方案的具体成本；生成后检查参数实际控制 host/kernel 的范围、循环与尾块。已有工具的真实读取记录可作来源证据，仅材料引用不能证明完整阅读，缺失写 unknown。事后复核单列，不补签历史。

正确性合同、reference、RNG、容差与输入域不变。资源合法不代表更快，精度通过不等于已完成语义审查，机械 audit 也不代替原流程。新实现不继承旧测量，源码/库/输入/构建/计时未变且已有有效证据时不重复测试。

## 阅读路径与来源

从[读取路由](../skills/ascend-op-workflow/references/tiling-knowledge/references/common/reading-routes.md)进入；[基础与增强入口](../skills/ascend-op-workflow/references/tiling-knowledge/INDEX.md)保留类别指南；[四份推理资料](../skills/ascend-op-workflow/references/tiling-knowledge/references/inference/knowledge-coverage.md)列出逐份覆盖。

来源清单见 [SHAPE_TILING_SOURCES.json](SHAPE_TILING_SOURCES.json)。50 文件的原快照中，49 份 Markdown 纳入知识范围，1 份 eval JSON 为既有测试样本，未当成领域知识或本轮测试结果分发。相比该快照的基础版本是 8 新增、9 修改、33 不变（含 eval）；不是只有新增卡片才属于知识。发行时的路由及用户四份资料蒸馏另列。
