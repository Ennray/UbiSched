# 精简后的代码阅读顺序

所有路径相对于项目根目录。当前只有一套正式运行入口和一套训练入口。

## 在线调度

| 顺序 | 文件或函数 | 要理解的内容 |
| --- | --- | --- |
| 1 | `ubisched/__main__.py:main` | 选择 serve、request、infer、worker 或 train |
| 2 | `ubisched/config.py` | 共享容量、单位、评分和输入约定 |
| 3 | `integration/policy.py:ModelPolicy` | 加载规则或学习模型，校验权重 |
| 4 | `integration/runtime.py:RuntimeCoordinator` | 保存状态、请求去重和事务 |
| 5 | `integration/runtime_server.py` | 接收 HTTP JSON 请求 |
| 6 | `integration/scheduler.py:SchedulerLoop` | 初始化后自动发起调度 |
| 7 | `integration/snapshot.py:make_live_env` | 校验快照并恢复当前状态 |
| 8 | `graph/task_graph.py`、`graph/resource_graph.py` | 任务依赖、资源与通信条件 |
| 9 | `scheduling/multi_agent_env.py:observe` | 按 UAV 建立局部观测 |
| 10 | `scheduling/scheduler_env.py:observe` | 构造任务、资源、匹配及依赖特征 |
| 11 | `graph/match_matrix.py`、`graph/data_transfer.py` | 可行性、执行和通信估算 |
| 12 | `graph/action_mask.py` | 合法动作与等待动作 |
| 13 | `integration/policy.py:StructuredAdapter.decide` | 策略产生并复核联合分配建议 |
| 14 | `integration/runtime.py` 的 commit 分支 | 重新核验方案，登记占用并保存指令 |
| 15 | `integration/worker.py` | 领取指令，运行绑定程序，持久化并回报结果 |
| 16 | `integration/runtime.py:_feedback` | 释放资源、更新任务并允许后继就绪 |

第 13 步中，规则分支进入 `experiments/evaluation.py:choose_rule_actions`。
学习分支进入 `algorithms/transformer_mappo.py` 或 `algorithms/mappo_baseline.py`。
依赖增强模型先聚合后继信息，再联合编码任务和资源并对组合评分。
所有模型都使用动作掩码；联合选择还会排除已被前一 UAV 认领的任务。

规划时只修改临时副本，正式占用发生在 commit。
在线完成任务必须收到反馈，不能用预计结束时间代替反馈。

## 训练

从 `python -m ubisched train` 进入 `ubisched/training.py:main`。

1. `experiments/integrated_scenario.py` 生成训练及测试场景。
2. `config.py:make_env` 创建统一多智能体环境。
3. `MAPPOBaseline.sample_episode` 收集完整回合。
4. `MultiAgentSchedulerEnv.step` 执行联合动作。
5. `AssignmentExecutor.assign` 登记分配，仿真按估计时长推进事件。
6. `MAPPOBaseline.update` 计算 GAE、PPO 目标、价值损失和梯度更新。
7. `training.py` 保存权重，再冻结策略运行独立测试。
8. 输出逐案例指标、按种子汇总和跨种子汇总。

训练使用仿真事件完成任务，在线运行使用执行反馈，两者共用建模和评分规则。
四种模型都保留，方便基线与消融比较。

## 示例与测试

`scripts/` 只有完整演示和模拟执行器。模拟执行器不提供真实性能数据。
`tests/support/` 是算法及边界测试的辅助场景，不属于运行或训练流程。
当前核心包不导入 `tests`，也不依赖旧 C++ 或旧算法工程。

## 路径变更

| 旧路径 | 当前路径 |
| --- | --- |
| `scripts/run_stage11_integrated.py` | `ubisched/training.py` |
| `ubisched/integration/structured_bridge.py` 中的推理部分 | `ubisched/integration/policy.py` |
| `ubisched/experiments/scenarios.py` | `tests/support/scenarios.py` |
| `ubisched/experiments/link_contention.py` | `tests/support/link_contention.py` |
| `scripts/train_mappo_baseline.py` 中测试使用的小场景 | `tests/support/baseline_env.py` |

旧 UDP 服务、编号翻译和旧规则调度器已从本分支移除。
