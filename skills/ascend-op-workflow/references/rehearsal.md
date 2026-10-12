# 生成→优化接线演练

用于用户明确要求测试工作流而不执行算子生成的场景。整个演练不调用build/precision/performance/NPU，不启动真实优化搜索。

1. 核实目标环境、仓库、适用指令、generator和evolution入口。选择简单torch组合或已有小案例作为输入；输入数值可以CPU构造，但不能冒充性能测试。
2. 在独立run记录 `mode=rehearsal`，合同标记 provisional/NOT_RUN，写实际shape推导、definition、workload和reference，通过目标benchmark真实schema/loader读取，归档case ID及输出。冻结演练材料是为了复现接线，不表示正式NPU合同已经验收。
3. 按主skill生成generation handoff。独立执行Agent实际读取生成技能及适用阶段，进入准备阶段，输出接收确认、输入映射、设计提纲和文件地图。不仅生成一份未被读取的prompt。核对生成器实际要求的 model.py/输入组接口，补齐适配文件并保留 case ID 映射；不能把不兼容的原始源码当作已接通入口。若实际 prepare_workspace 仅做获准目录中的文件准备，可执行并保存日志；缺少依赖时分别报告静态接口检查与运行检查。
4. 创建synthetic生成产物，例如 `model_new_ascendc.py` 入口明确 `raise RuntimeError('REHEARSAL_ONLY')`、设计文档、null精度性能结果及manifest。这些是流程测试数据，不是实现。
5. 将该目录交给优化准备流程。实际读取优化skill/角色和其适用资源，演练起点标记 `synthetic_G`、`validated_G=false`，确认目标G/O=1.5、5轮×5候选，并输出接收确认与首轮5候选的待执行计划。接收记录包含实际skill路径/哈希/读取章节和PREPARED_ONLY。它们只可标PLANNED；不得写PASSED/MEASURED，也不初始化需要真实baseline PASS的搜索阶段。
6. 主协调者核对中间文件、实际loader证据、双方skill读取/接收记录、路径引用与hash；归档后的引用应使用稳定包身份与包内路径，不依赖复制前的相对目录。检验演练产物无法通过正式优化门禁，保存真实拒绝命令和退出码。下游没有可安全运行的只读检查时，明确仅验证本编排层的生产隔离，不称下游engine也已验证。
7. 输出REHEARSAL_REPORT，逐步列完成/失败、真实执行命令及退出码、未运行部分和修复后复测。只可结论“benchmark接入与阶段准备交接通过”；真实生成/编译/精度/性能/优化搜索仍未验证。

如果下游技能没有显式dry-run命令，不发明参数或修改共享门禁。以编排层的准备模式读取技能并产出接收计划，明确这种验证不等于执行下游engine。用户以后要求实际跑算子时另建production run。
