# 新版代码阅读顺序

当前入口已经调整为 `ubisched/__main__.py`。`structured_bridge.py` 是推理模块和历史无状态服务入口，不再承担完整新版系统的启动入口。
阅读时以一次真实调用为主线。进入被调用函数，看完后回到原调用处继续。主流程结束后，再补读训练、异常、可选算法和历史脚本。

本清单覆盖新版 Python 核心与脚本。旧 C++ 与旧算法工程只在兼容部分说明，不把它们混入新版必经流程。

## 1. 启动服务

命令 `python -m ubisched serve --auto-schedule`。

| 顺序 | 位置 | 要理解的内容 |
| --- | --- | --- |
| 1 | `ubisched/__main__.py` 的 `main()` | Python 如何进入项目，选择 serve 而非训练或 worker |
| 2 | `ubisched/config.py` | 全部容量、单位、评分、归一化和模型输入约定 |
| 3 | `structured_bridge.py` 的 `ModelPolicy.__post_init__()` | 加载哪个模型，如何核对输入约定 |
| 4 | `ModelPolicy._initialize_algo()` | 缓存并预热模型，不在每轮重新加载 |
| 5 | `runtime.py` 的 `RuntimeCoordinator.__init__()` | 数据库、请求去重表和状态恢复 |
| 6 | `runtime_server.py` | 接收 JSON 请求并转交协调器 |
| 7 | `scheduler.py` | 自动调度线程，初始化之前等待有效状态 |

这里还没有分配任务，只是创建了能够接收输入、调度和恢复状态的服务。

## 2. 接收任务和资源

入口是 initialize 请求。继续跟随 `RuntimeCoordinator.handle()` 和 `_execute()`。

先看请求编号查重、事务和异常回滚，再看 initialize 分支。
`snapshot.py` 的 `make_live_env()` 检查字段、单位、任务依赖和资源归属，然后恢复环境。

依次进入以下文件。

1. `graph/task_graph.py`，读 SubTask、TaskEdge、TaskGraph 和就绪状态更新。
2. `graph/resource_graph.py`，读资源、归属和通信路径。
3. `scheduling/multi_agent_env.py`，看如何按 UAV 分组。
4. `scheduling/scheduler_env.py`，看基础环境和数字特征。
5. `scheduling/scheduling_state.py`，看状态、分配记录和通信预约。
6. 回到 `snapshot.py`，看已完成、运行中和传输记录如何恢复。
7. 回到 `runtime.py`，看 `state_snapshot()` 如何保存状态。

这里的 SchedulerEnv 属于新版公共环境，被多智能体环境复用。它不是旧能力需求表流程。

## 3. 一轮完整决策

自动线程调用 schedule，手动请求也可以先 plan 再 commit。

| 顺序 | 调用 | 内容 |
| --- | --- | --- |
| 1 | runtime 的 schedule/sweep | 更新任务时间，检查指令是否超时 |
| 2 | runtime 的 plan | 取当前状态，记录决策耗时 |
| 3 | `StructuredAdapter.decide()` | 从快照建立本轮环境 |
| 4 | `MultiAgentSchedulerEnv.observe()` | 为各 UAV 组织局部观测 |
| 5 | `SchedulerEnv.observe()` | 数字化任务、资源和匹配关系 |
| 6 | `AssignmentExecutor.build_match_matrix()` | 对当前图重新计算匹配 |
| 7 | `graph/data_transfer.py` | 查前驱数据在哪里，估算传输、排队和能耗 |
| 8 | `graph/match_matrix.py` | 硬约束、时延和质量评分 |
| 9 | `graph/action_mask.py` | 合法动作、动作编号和等待动作 |
| 10 | `graph/dependency_features.py` | 任务邻接关系及下游特征 |
| 11 | `ModelPolicy.choose()` | 分别进入规则策略或学习策略 |

模型主分支继续读 `algorithms/transformer_mappo.py`。

1. `_make_actor_inputs()` 把观测整理成任务、资源、匹配及依赖张量。
2. `DependencyAwareTaskResourceActor._embed_task_nodes()` 聚合后继信息。
3. `TaskResourceTransformerActor.forward()` 处理任务和资源 token，再给每个任务与资源组合打分。
4. 返回 `algorithms/mappo_baseline.py` 的 `select_actions()`。
5. 看非法动作屏蔽、前面 UAV 已选任务的排除，以及避免全部无意义等待的处理。
6. 回到 `StructuredAdapter.decide()`，还原真实任务与资源编号。
7. 在临时环境内依次核验联合动作，避免方案内部相互超用资源或能量。
8. 返回方案。此时还没有实际提交给执行端。

规则分支进入 `experiments/evaluation.py` 的 `choose_rule_actions()`，它复用同一约束和评分。

## 4. 从方案到指令

回到 runtime 的 commit 分支。

检查 plan 的状态版本，重新核验全部分配，调用 `AssignmentExecutor.assign()` 登记占用、预计能耗和通信预约。
随后生成 command_id、执行端归属、任务参数和前驱数据引用。
任务、指令和请求去重响应在同一个 SQLite 事务里保存。任意一步失败都回滚。

注意这里使用 assign 预留资源，但不会调用仿真的 advance_time 来自动完成任务。

## 5. 执行与结束

另一个进程从 `__main__.py` 的 worker 分支启动。

1. `worker.py` 读取资源与本机程序的配置。
2. `client.py` 向运行服务发送 poll_commands。
3. runtime 校验 UAV 和 worker 归属，返回持有原 command_id 的指令。
4. worker 查本机数据库，已经启动的指令不会再次执行。
5. worker 回报 running，然后并行启动不同资源的程序。
6. 程序返回结果，worker 先持久化结果，再发送 feedback。
7. runtime 的 `_feedback()` 校验归属和时间，只处理当前指令对应的分配。
8. 成功则任务 finished，失败则任务 failed，同时释放资源并更新通信记录。
9. 后继任务满足条件后进入 ready，自动线程继续下一轮。
10. `state` 的 summary 显示全部任务完成后，整个任务集合结束。服务仍可查询记录。

离线完整示例为 `scripts/demo_v2_runtime.py`。它使用 `scripts/mock_executor.py` 代替真实执行程序。
读完这两份文件，需要能够分清真实反馈接口与演示反馈数据。

## 6. 动态变化和异常分支

主流程读完后，逐项进入 runtime 对应分支。

- 重复请求、不同内容重复使用同一编号、事务回滚。
- 旧方案版本、并发提交和整个批次的核验。
- `telemetry.py` 的生产端及旧评估分数转换。
- 新增任务和新增资源，容量超限的处理。
- 资源掉线、通信中断、主动取消和执行超时。
- 停止尚未确认时继续保留资源占用。
- 失败后的显式重试，以及旧指令迟到反馈。
- 服务恢复、worker 恢复和 recovery_required。
- 执行能耗实测值、估计值和前驱输出数据的区别。

结合 `tests/test_v2_runtime.py` 阅读上述分支，确认每种情况改变哪些状态。

## 7. 训练到输出文件

从 `python -m ubisched train` 回到 `scripts/run_stage11_integrated.py` 的 main。

先看 `experiments/integrated_scenario.py` 怎样创建任务和资源，再看 make_env 复用的共同配置。
依次跟踪 MAPPO 的 sample_episode、MultiAgentSchedulerEnv.step、AssignmentExecutor.assign 和 advance_time。
训练环境使用估计时长推进时间，在线系统根据反馈推进任务状态。两种行为不要混淆。

然后读 MAPPO 的 GAE、PPO clip、集中式 Critic、熵和梯度更新，最后读 checkpoint 保存的输入约定。
回到训练脚本，跟随 evaluate、run_episode、CSV 输出及跨种子汇总，直到 main 返回。

测试种子与训练种子分离，规则和学习策略共享场景。但这只是实验代码设计，充分实验仍需要单独进行。

## 8. 可选模型和早期新版模块

`transformer_mappo.py` 的四种模型均需阅读。

| 模型 | 阅读重点 |
| --- | --- |
| MLP-MAPPO | 扁平输入基线，位于 mappo_baseline.py |
| 普通 Transformer | 任务与资源注意力，没有显式依赖消息聚合 |
| 依赖增强 Transformer | 当前默认主模型，先做两次后继消息聚合 |
| 关键路径增强 Transformer | 再加入 critical_path.py 估计的时间预算特征 |

关键路径是忽略未来竞争和通信拓扑的近似估计，不是最优调度结果。
`scheduling/rule_based_scheduler.py` 属于早期新版独立调度器，主服务不调用它，结合其示例脚本补读。
`experiments/scenarios.py`、`sensing_compute.py`、`link_contention.py` 分别用于早期基线、感算任务和通信争用场景。

## 9. 兼容部分

最后单独读 `integration/is2ros_bridge.py`、`iSSROS/core/UbiSchedBridgeClient.h`、`UbiSchedStructuredClient.h`。
再读 C++ 的 CapAdaptiveManager 与 CapDispatchManager，理解旧格式兼容的限制和显式回退开关。
旧 C++ main、CapEngine、能力表和插件的完整旧逻辑，不属于新版主流程。
如果以后专门核对旧系统，可以独立阅读，不能用旧系统的入口来代替本清单第 1 步。

## 10. 全文件核对

后附自动生成的新版模块、脚本与测试列表。阅读过程中应逐个标记，不能只读主入口就认为覆盖了整个新版。

### 核心模块

- [ ] `ubisched/__init__.py`
- [ ] `ubisched/__main__.py`
- [ ] `ubisched/algorithms/__init__.py`
- [ ] `ubisched/algorithms/mappo_baseline.py`
- [ ] `ubisched/algorithms/transformer_mappo.py`
- [ ] `ubisched/config.py`
- [ ] `ubisched/experiments/__init__.py`
- [ ] `ubisched/experiments/evaluation.py`
- [ ] `ubisched/experiments/integrated_scenario.py`
- [ ] `ubisched/experiments/link_contention.py`
- [ ] `ubisched/experiments/scenarios.py`
- [ ] `ubisched/experiments/sensing_compute.py`
- [ ] `ubisched/graph/action_mask.py`
- [ ] `ubisched/graph/critical_path.py`
- [ ] `ubisched/graph/data_transfer.py`
- [ ] `ubisched/graph/dependency_features.py`
- [ ] `ubisched/graph/match_matrix.py`
- [ ] `ubisched/graph/resource_graph.py`
- [ ] `ubisched/graph/task_graph.py`
- [ ] `ubisched/integration/__init__.py`
- [ ] `ubisched/integration/client.py`
- [ ] `ubisched/integration/is2ros_bridge.py`
- [ ] `ubisched/integration/runtime.py`
- [ ] `ubisched/integration/runtime_server.py`
- [ ] `ubisched/integration/scheduler.py`
- [ ] `ubisched/integration/snapshot.py`
- [ ] `ubisched/integration/structured_bridge.py`
- [ ] `ubisched/integration/telemetry.py`
- [ ] `ubisched/integration/worker.py`
- [ ] `ubisched/scheduling/__init__.py`
- [ ] `ubisched/scheduling/assignment_executor.py`
- [ ] `ubisched/scheduling/multi_agent_env.py`
- [ ] `ubisched/scheduling/rule_based_scheduler.py`
- [ ] `ubisched/scheduling/scheduler_env.py`
- [ ] `ubisched/scheduling/scheduling_state.py`

### 演示、训练和辅助脚本

- [ ] `scripts/__init__.py`
- [ ] `scripts/demo_build_match_matrix.py`
- [ ] `scripts/demo_dynamic_scheduling.py`
- [ ] `scripts/demo_multi_agent_env.py`
- [ ] `scripts/demo_online_scheduling.py`
- [ ] `scripts/demo_rule_based_scheduling.py`
- [ ] `scripts/demo_scheduler_env.py`
- [ ] `scripts/demo_stage10_network_scheduling.py`
- [ ] `scripts/demo_stage12_bridge_client.py`
- [ ] `scripts/demo_stage13_online.py`
- [ ] `scripts/demo_stage9_sensing_compute.py`
- [ ] `scripts/demo_v2_runtime.py`
- [ ] `scripts/inspect_stage5_failures.py`
- [ ] `scripts/mock_executor.py`
- [ ] `scripts/run_stage11_integrated.py`
- [ ] `scripts/run_stage12_bridge.py`
- [ ] `scripts/run_stage4_benchmark.py`
- [ ] `scripts/run_stage5_diagnostics.py`
- [ ] `scripts/run_stage6_transformer.py`
- [ ] `scripts/run_stage7_dependency.py`
- [ ] `scripts/run_stage8_critical_path.py`
- [ ] `scripts/stage12_cpp_probe.cpp`
- [ ] `scripts/stage13_cpp_probe.cpp`
- [ ] `scripts/train_mappo_baseline.py`
- [ ] `scripts/write_stage13_snapshot.py`

### 测试

- [ ] `tests/test_action_mask.py`
- [ ] `tests/test_dynamic_scheduling.py`
- [ ] `tests/test_mappo_baseline.py`
- [ ] `tests/test_match_matrix.py`
- [ ] `tests/test_multi_agent_env.py`
- [ ] `tests/test_online_scheduling.py`
- [ ] `tests/test_resource_graph.py`
- [ ] `tests/test_rule_based_scheduler.py`
- [ ] `tests/test_scheduler_env.py`
- [ ] `tests/test_stage10_link_scheduling.py`
- [ ] `tests/test_stage11_end_to_end.py`
- [ ] `tests/test_stage12_bridge.py`
- [ ] `tests/test_stage12_cpp_adapter.py`
- [ ] `tests/test_stage12_match_capability.py`
- [ ] `tests/test_stage13_cpp_adapter.py`
- [ ] `tests/test_stage13_structured_bridge.py`
- [ ] `tests/test_stage4_experiments.py`
- [ ] `tests/test_stage5_coordination.py`
- [ ] `tests/test_stage6_transformer.py`
- [ ] `tests/test_stage7_dependencies.py`
- [ ] `tests/test_stage8_critical_path.py`
- [ ] `tests/test_stage9_communication.py`
- [ ] `tests/test_task_graph.py`
- [ ] `tests/test_v2_cli.py`
- [ ] `tests/test_v2_model_variants.py`
- [ ] `tests/test_v2_runtime.py`
