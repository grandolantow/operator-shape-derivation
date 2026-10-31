# 性能集合与逐轮分析

## 首版轻量验收

先直接生成首版或复用已知实现，再完成全量正确性与一次正式性能验收决策。auto达标即交付G，未达标才进入优化；轻量不减少测量重复次数、正确性范围或原始证据检查。首版、各轮候选和最终对照使用同一冻结性能集，不能为了改善成绩更换用例。

## 两套集合

正确性始终验证完整workload。性能固定10例，超大例最多3例。先按输入几何、估算算量和逻辑存储规模定义阈值/OR或AND关系并分类，再选代表性case；不能按候选成绩挑例。逻辑score矩阵规模不是融合kernel实际峰值内存。覆盖dtype、规模、边界与尾块；完整集合不足10例时报告缺口，不复制case凑数。

`workflow.py init --case-manifest`读取一个同时包含两套集合的JSON：

```json
{
  "case_ids": ["完整正确性ID，至少覆盖全部正式输入"],
  "performance_case_ids": ["恰好10个唯一且属于case_ids的ID"],
  "performance_selection": {
    "policy": "fixed10-v1",
    "ultra_large_case_ids": ["其中至多3个ID"],
    "classification": {
      "definition": {"formula": "实际算量/逻辑存储估算公式", "threshold": "运行前确定的阈值"},
      "cases": {"每个完整caseID": {"ultra_large": false, "estimated_flops": 0, "logical_workspace_bytes": 0}}
    }
  }
}
```

这是结构示意；实际文件须完整列出所有ID、10个性能ID及实值。CLI检查集合、分类覆盖及超大标签一致性，不能替代对算量公式和代表性的审查。两套集合/分类纳入不可变身份，变更需新关联run，不能改旧run.json。

生产evidence顶层 `case_ids` 和 `correctness.case_ids` 保持完整；新增 `performance_case_ids` 必须与冻结子集相同，`baseline_us` / `candidate_us`只覆盖该子集。历史run不含新字段时继续使用旧的全量计时语义，不修改旧证据。

实际 runner 也必须分离：生成验收、逐候选性能及下游 engine_score 均只采固定10例，正确性 callback 验全量。交接时显式提供两套 manifest/参数及同一输入ID映射，检查实际日志数量；不能只在最终报告截取10例而让内部默认反复测全量。原工具不能分离时仅在任务工程增加适配入口，保留原评测调用与原始日志；不修改共享 CANNBot。

## 每轮结束

逐个候选读取真实终态、完整精度和10例性能，定位绝对耗时大的case及相对固定G/上一冠军的退化。区分计算、搬运、启动/同步、布局转换等观察与因果假设。没有PMU/trace不虚构硬件bound标签。

将分析写成JSON，运行：

```text
python workflow.py round-review --run RUN --record ROUND_REVIEW.json
python workflow.py round-check --run RUN --next-round 2
```

新正式run自动启用逐轮分析；init按任务合同传入预算和搜索宽度，例如 `--optimization-seconds 18000 --rounds 5 --variants 5`。用户指定的时间、轮数或宽度优先。优化prepare必须显式传 `--round N`；每轮SELECT/派发前必须实际调用round-check。已完成轮次不能重开，stop或最终轮后禁止进一步派发；同轮review修订只可在后续轮review之前追加。它不会自动调度agent或替换下游世界模型。

review必需字段：

- `round`：实际轮次；`candidates`：每个候选槽一项，唯一candidate_id。
- 每项 `status` 为 evaluated / precision_failed / build_failed / timeout / cancelled / static_rejected；`artifacts`引用现存原始证据。
- `analysis.status`为confirmed / hypothesis / unknown；`observations`、`explanation`、`next_experiment`、`expected_observation`均为具体文本。evaluated项的 `slow_cases`至少一项，每项含冻结性能case_id、baseline_us、candidate_us；另记上一冠军和原始采样引用。未生成性能的失败项可为空，不等待永远不会出现的性能文件。
- `next_round_candidates`：非最终轮按搜索宽度列出下一轮假设，每项含hypothesis_id、mechanism_change、rationale、falsifier、source_candidate_ids（本轮证据）、expected_case_ids（冻结性能集）。组合须说明机制如何互补及如何区分收益来源。
- 最终轮或预算结束时next_round_candidates为空；提前结束加真实stop_reason。

归档追加保存原review和引用证据并校验哈希。记录/计数/字段完整不证明因果解释正确，协调者仍须复核原始数据与实验区分能力。unknown附具体实验可继续，不以编造标签换取通过。

新review另冻结 `review.json` 回执，绑定原文、轮次、追加顺序和是否允许下一轮；可修改的索引必须与回执一致。无该回执的历史review仍可读取及验证文件，但不能自动证明派发顺序，`round-check`会停止续跑。先独立核查原文与实际执行；如需关联新run，保留旧档、固定G及已消耗预算，不回填旧哈希或重置预算。

## 根因分析约束与实现选择

- 每轮分别对比固定G、上一冠军，以及任务提供的旧实现；既看整体GM，也列出慢例和局部退化。按dtype、输入几何、尾块等可解释特征分组，不把整体收益当作每个case都受益。
- 分清实现问题与搜索策略问题：实现上检查计算路径、冗余转换/补齐、GM中间结果、kernel启动及同步；策略上检查搜索是否遗漏结构替换，或只在同一低效结构内改参数。没有profile证据时标为假设，并给出能区分原因的实验。
- 每个候选说明改变的机制、保持不变的条件、预期受益case和反证；组合候选必须能解释各因素贡献，避免纯排列组合。连续多轮相同慢例无改善时重新检查算法/流水/数据布局假设，不强制保留首版结构。
- 结构调整可以是融合、拆分、复用库实现或按形状分支；依据真实语义特征分派，不能按benchmark case ID硬编码。涉及布局/同步/缓冲生命周期变化时重新审查相应正确性。
- 在合同中预先明确可接受退化和连续无收益的早停条件，不在看到结果后挑阈值。交付前复核固定10例的逐例表现与全量正确性；没有可确认改进就保留G，并明确目标未达。CLI检查证据结构与GM，逐例退化政策和因果质量由协调者核查。
