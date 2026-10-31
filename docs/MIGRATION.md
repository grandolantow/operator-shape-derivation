# 从shape独立仓迁移

原Git仓库与历史保留，原shape文件（包括未提交修订）移动到skills/operator-shape-derivation；不是用旧发行快照覆盖。主工作流加入skills/ascend-op-workflow。两份技能分别维护各自职责，本仓统一发布。

兼容入口：
- 根SKILL.md仍叫operator-shape-derivation，转向完整shape技能；已有克隆到技能搜索路径或用户级目录链接继续可用。
- scripts/check_execution_contract.py保留CLI退出码/JSON及Python导入的validate_contract接口，转调新位置。
- 仅shape使用者不需要安装完整套件或外部CANNBot；完整任务使用根安装器。
- 未将个人配置、凭据、远端状态、历史任务产物迁入Git仓库。

目标仓库名称为ascend-op-workflow。远端改名尚未完成：当前GitHub CLI未认证，原origin仍是https://github.com/grandolantow/operator-shape-derivation.git。完成远端改名后更新origin与本文件；本地目录名不影响技能或安装器。旧URL跳转需在实际改名后验证，不提前承诺。

本仓是后续工作流与shape的唯一维护源。项目workflow和CANNBot内旧工作流目录仅保留历史快照，不再双向编辑；现存CANNBot改动和历史PR没有被清理或自动关闭。
