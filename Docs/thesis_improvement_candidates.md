# 硕士毕设优化候选问题与方案

## 1. 总体判断

当前项目已经有一个可作为论文工程基础的框架：

```text
iS2ROS C++ 运行框架
  -> UDP 接收仿真状态
  -> 能力/资源对象建模
  -> 插件化评估与选择接口
  -> C++ 调 Python MAPPO actor
  -> UDP 输出调度结果
```

但从“基于多智能体强化学习的异构 UAV 集群感知资源与计算任务协同实时调度”这个论文目标看，当前系统还有明显空白：

- 异构 UAV 能力差异存在于 `sensors.txt` 和 `Capability` 对象中，但没有真正进入 MAPPO 决策。
- 感知资源属性没有系统性进入状态空间、动作空间、动作掩码和奖励函数。
- 计算任务、CPU 资源、计算负载、边缘处理时延、本地处理时延基本没有建模。
- 任务时长、截止时间、优先级、依赖关系没有建模。
- 资源容量约束和多 UAV 资源占用冲突只有很弱的任务级 mask，没有形成完整约束。
- 当前 MAPPO 的动作空间和智能体数量基本写死，泛化能力弱。
- C++ 调 Python 推理链路存在重复初始化、重复加载模型、接口语义不清晰等实时性问题。

因此，适合做毕业论文的方向不是“修 bug”，而是把现有框架扩展成一个具有明确状态、约束、奖励、实验指标的协同调度系统。

## 2. 问题分类

### 2.1 异构 UAV 能力差异未真正参与决策

| 问题 | 当前代码证据 | 论文价值 | 实现难度 | 预计工作量 | 对应可验证指标 |
| --- | --- | --- | --- | --- | --- |
| UAV 搭载能力差异没有进入 MAPPO 输入 | `sensors.txt` 中有 `EOCap`、`IRCap`、`power`、`level`，但 `CapAdaptiveManager` 构造 `obs` 时只使用 `obs0` | 高 | 中 | 2-4 周 | 任务完成率、资源匹配成功率、无效动作率、异构场景收益 |
| UAV 编号只用于加载 actor 权重，不作为状态特征 | `new.py` 用 `UAVid` 选择 `actor_agent{UAVid-1}.pt` | 中 | 低 | 1 周 | 不同 UAV 能力变化后的策略适应性 |
| 资源评估结果未进入选择 | `AssessPlugin` 会追加 `Capability.level`，但选择插件接口不接收 `resourceCapTB` | 高 | 中 | 2-3 周 | 环境恶化下的任务成功率、感知质量、平均能力利用率 |
| 资源所属 UAV 与下发 UAV 没有严格绑定 | `CapDispatchManager` 使用 `"UAV"+to_string(UAVid)`，不是按 `Capability.vehicleName` 匹配 | 中 | 中 | 1-2 周 | 错误分配率、跨 UAV 资源冲突次数 |

论文意义：

当前代码可以作为“基线系统”，改进点是提出“面向异构能力的资源感知 MAPPO 状态建模与动作约束方法”。这比单纯修复资源表读取更适合形成论文贡献。

### 2.2 感知资源属性未进入状态空间、动作空间、动作掩码和奖励函数

| 问题 | 当前代码证据 | 论文价值 | 实现难度 | 预计工作量 | 对应可验证指标 |
| --- | --- | --- | --- | --- | --- |
| 状态空间没有资源特征 | `obs = obs0` 字符级转换；训练环境 `EnvCore.obs_dim=15` 只表达任务状态和环境因子 | 高 | 中 | 2-4 周 | 平均回报、收敛速度、泛化测试得分 |
| 动作空间只选 `[task_idx, sensor_idx]`，没有选择真实资源实例 | `EnvCore.action_dim=[5,4]`，dispatch 输出 `taskid#imageType#UAVid` | 高 | 中高 | 3-5 周 | 资源实例匹配率、资源利用率、冲突率 |
| 传感器动作掩码固定 | C++ 在线 `sensors={1,1,1,0}`；训练环境也初始化 `[1,1,1,0]` | 高 | 中 | 2-3 周 | 无效动作率、资源不可用场景任务成功率 |
| 奖励函数没有使用真实能力属性 | `EnvCore.step()` 奖励主要由任务类型、sensor 编号、随机 weather 因子计算 | 高 | 中 | 2-4 周 | 感知质量得分、能耗、完成时延、综合效用 |
| 资源功耗、分辨率、视场角、位置没有闭环 | `Capability` 中存在，MAPPO 不读取 | 中高 | 中 | 2-4 周 | 单位能耗完成任务数、覆盖率、感知质量 |

论文意义：

这是最直接、最稳妥的论文主线。可以提出“资源属性增强状态 + 动态动作掩码 + 多目标奖励”的 MAPPO 改进版本，并与原始固定 mask MAPPO 做对比。

### 2.3 计算任务与计算资源没有建模

| 问题 | 当前代码证据 | 论文价值 | 实现难度 | 预计工作量 | 对应可验证指标 |
| --- | --- | --- | --- | --- | --- |
| 没有计算负载字段 | `Capability` 描述感知能力，没有 CPU、GPU、memory、queue 等字段 | 高 | 中 | 2-3 周 | 计算资源利用率、平均处理时延 |
| 没有本地/边缘处理时延模型 | 现有 dispatch 只下发 `taskid#imageType#UAVid` | 高 | 中高 | 3-5 周 | 端到端时延、截止时间满足率 |
| 没有任务卸载决策 | 动作空间没有 `local/edge/UAV-peer` 等计算位置选择 | 高 | 高 | 4-6 周 | 卸载比例、能耗-时延 Pareto 指标 |
| 没有计算队列和排队时延 | 训练环境没有队列状态 | 中高 | 中 | 2-4 周 | 平均排队时延、最大积压任务数 |
| 感知与计算没有协同优化 | 资源选择只选择传感器编号，不考虑检测/识别后处理成本 | 高 | 高 | 4-8 周 | 综合任务效用、任务超期率、资源负载均衡 |

论文意义：

这是最贴近你的题目“感知资源与计算任务协同实时调度”的方向。工作量充足，但要注意控制范围，建议先做简化计算模型，而不是一开始引入完整边缘云系统。

可采用的简化建模：

```text
每个任务:
  data_size
  cpu_cycles
  deadline
  priority

每个 UAV/edge:
  cpu_freq
  available_cpu
  queue_length
  link_rate
  energy_coeff

时延:
  sensing_time + transmission_time + queue_delay + compute_time

奖励:
  task_success_reward
  - latency_penalty
  - energy_penalty
  - deadline_violation_penalty
```

### 2.4 任务执行时长、截止时间、优先级和依赖关系没有建模

| 问题 | 当前代码证据 | 论文价值 | 实现难度 | 预计工作量 | 对应可验证指标 |
| --- | --- | --- | --- | --- | --- |
| 任务持续时间固定或缺失 | `CapabilityNeed::add(id,10,0.8)` 中时间固定为 10，训练环境没有执行时长 | 高 | 中 | 2-3 周 | 平均完成时间、makespan |
| 没有 deadline | 任务完成只看 `last_obs[task]=0` | 高 | 中 | 2-3 周 | 截止时间满足率、超期惩罚 |
| 没有 priority | 奖励没有任务优先级权重 | 中高 | 低中 | 1-2 周 | 高优先级任务完成率、加权任务收益 |
| 没有依赖关系 | 每个任务独立，可任意选择 | 中高 | 中高 | 3-5 周 | 依赖违反次数、工作流完成率 |
| 没有任务生命周期 | 没有 pending/running/done/failed/expired 等状态 | 高 | 中 | 2-4 周 | 状态转移正确率、在线调度稳定性 |

论文意义：

任务时序约束适合增强论文深度。尤其是 deadline 和 priority，改动相对可控，实验指标清晰。任务依赖关系价值高，但实现复杂度更大，建议作为增强实验或扩展章节。

### 2.5 任务容量约束和资源占用冲突不足

| 问题 | 当前代码证据 | 论文价值 | 实现难度 | 预计工作量 | 对应可验证指标 |
| --- | --- | --- | --- | --- | --- |
| 同一 UAV 同时执行多个任务的容量约束不足 | 只有训练 runner 中临时屏蔽已选任务，在线 C++ 没有全局资源占用表 | 高 | 中 | 2-3 周 | 资源冲突次数、任务排队长度 |
| 同一传感器是否被占用没有建模 | 动作 mask 不考虑传感器 busy/idle | 高 | 中 | 2-3 周 | 传感器冲突率、有效调度率 |
| 资源释放时刻没有建模 | 没有任务执行时长，也没有资源释放事件 | 高 | 中 | 2-4 周 | 资源利用率、平均等待时间 |
| 多 UAV 冲突解决机制弱 | 训练中有浅拷贝 mask 和顺序屏蔽，在线每个 UAV 独立推理 | 中高 | 中高 | 3-5 周 | 冲突动作率、协同效率 |
| 容量约束没有进入奖励 | 冲突和超载没有显式惩罚 | 高 | 中 | 2-3 周 | 约束违反率、约束满足回报 |

论文意义：

这是“资源调度”区别于“动作分类”的关键。建议用动态资源占用表和动作掩码表达硬约束，用奖励函数表达软约束。

### 2.6 MAPPO 动作空间、泛化和规模适应性问题

| 问题 | 当前代码证据 | 论文价值 | 实现难度 | 预计工作量 | 对应可验证指标 |
| --- | --- | --- | --- | --- | --- |
| 动作空间固定为 5 个任务、4 类传感器 | `EnvCore.obs_dim=15`，`action_dim=[5,4]`，多处硬编码 5 | 高 | 中高 | 3-5 周 | 不同任务数下的性能保持率 |
| 智能体数量固定或不一致 | 训练 `agent_num=2`，权重目录叫 `5UAVs`，C++ 按 UAVid 加载 5 个 actor | 高 | 中高 | 3-5 周 | 2/3/5 UAV 泛化性能 |
| 独立 actor 对规模变化适应弱 | 每个 agent 独立 actor 文件，新增 UAV 需要新权重 | 中高 | 中高 | 3-5 周 | 新 UAV 加入后的无需重训性能 |
| 动作空间随任务和资源增长会膨胀 | 若扩展为任务-资源-计算节点组合，直接 MultiDiscrete 会变大 | 高 | 高 | 4-8 周 | 收敛速度、动作无效率、训练稳定性 |
| 状态是固定长度向量，难表达可变任务/资源集合 | 当前 obs 固定长度 | 高 | 高 | 4-8 周 | 可变规模泛化实验得分 |

可选技术路线：

- 轻量路线：固定最大任务数/资源数，使用 padding + mask。
- 中等路线：共享策略 + 参数共享 actor，支持不同 UAV 数量。
- 高阶路线：使用注意力机制、图神经网络或 pointer-style policy 表达任务-资源二部图。

论文意义：

规模泛化是很好的创新点，但风险较高。硕士毕设建议选择“共享策略 + padding/mask + 规模泛化实验”，不要一开始就重写成复杂图网络。

### 2.7 C++ 与 Python 调用链路工程问题

| 问题 | 当前代码证据 | 论文价值 | 实现难度 | 预计工作量 | 对应可验证指标 |
| --- | --- | --- | --- | --- | --- |
| 每次选择都可能初始化 Python | `SelectPlugin::select()` 中调用 `Py_Initialize()` | 中 | 中 | 1-2 周 | 单次推理延迟、延迟方差 |
| 每次推理都加载 actor 权重 | `new.py::actor_inference()` 每次创建 actor 并 `load_state_dict` | 高，偏工程系统 | 中 | 2-3 周 | 平均推理时延、最大推理时延 |
| C++/Python 接口语义不清晰 | 参数只有 `obs`、`rnn_states`、`available_actions`、`UAVid`，没有结构化任务/资源字段 | 中高 | 中 | 2-3 周 | 接口字段完整性、异常输入处理率 |
| 在线推理没有维度校验 | `obs0.length()` 任意，Python actor 期望训练维度 | 中 | 低 | 1 周 | 输入异常检出率、推理失败率 |
| 插件每轮动态加载 | `CapAdaptiveManager::run()` 中循环 `LoadLibrary` | 中 | 中 | 1-2 周 | 端到端调度周期 |
| 没有模型服务化或缓存 | actor、env space、Python module 没有持久化 | 中高 | 中 | 2-4 周 | 吞吐量、实时调度周期满足率 |

论文意义：

这类问题适合放在“系统实现与实时性优化”章节。单独作为论文主创新略偏工程，但与资源调度算法结合后可以形成完整系统工作量。

## 3. 候选问题优先级矩阵

| 优先级 | 候选方向 | 论文价值 | 实现风险 | 建议定位 |
| --- | --- | --- | --- | --- |
| A | 资源属性增强 MAPPO：状态、mask、奖励闭环 | 高 | 中 | 主创新一 |
| A | 感知-计算协同调度：负载、时延、能耗、deadline | 高 | 中高 | 主创新二 |
| A | 动态资源占用和冲突约束 | 高 | 中 | 主创新或关键模块 |
| B | 任务 deadline/priority 建模 | 中高 | 中 | 强化实验与指标 |
| B | 共享策略和规模泛化 | 高 | 中高 | 进阶创新 |
| B | C++/Python 推理缓存和实时性优化 | 中 | 中 | 系统实现章节 |
| C | 完整任务依赖 DAG | 中高 | 高 | 扩展工作 |
| C | 图神经网络/Transformer 可变规模调度 | 高 | 高 | 时间充足时再做 |

## 4. 适合硕士毕设的 3 个改进方案

### 方案一：资源属性感知的动态动作掩码 MAPPO

#### 方案名称

面向异构 UAV 感知能力的资源属性增强 MAPPO 调度方法

#### 要解决的问题

当前 MAPPO 没有真正使用 `sensors.txt` 和 `Capability` 中的异构资源属性。传感器 mask 固定为 `[1,1,1,0]`，导致策略不知道某架 UAV 真实拥有哪些传感器、能力强弱、功耗差异和环境退化后的能力变化。

#### 核心技术

- 将资源属性加入状态空间：
  - 资源是否在线
  - EO/IR 类型
  - 能力等级 `level`
  - 功耗 `power`
  - 分辨率、视场角编码
  - 环境评估后的动态能力得分
- 根据资源表生成动态动作掩码：
  - 当前 UAV 不具备的资源 mask 为 0
  - 离线资源 mask 为 0
  - 能力不满足任务需求时 mask 为 0 或给予强惩罚
- 改造奖励函数：
  - 任务成功奖励
  - 感知质量奖励
  - 能耗惩罚
  - 选择不可用资源惩罚
- 保持动作形式为 `[task_idx, sensor_type]` 或小幅扩展为 `[task_idx, resource_type]`，避免动作空间过大。

#### 需要修改的文件

训练侧：

- `light_mappo-transformer/light_mappo-main/envs/env_core.py`
- `light_mappo-transformer/light_mappo-main/envs/env_discrete.py`
- `light_mappo-transformer/light_mappo-main/config.py`
- `light_mappo-transformer/light_mappo-main/runner/separated/env_runner.py`

在线侧：

- `iSSROS/core/CapAdaptiveManager.cpp`
- `iSSROS/CapInterface/CapInterfaceManager.cpp`
- `plugins/select/SelectAPI.h`
- `plugins/select/selectPlugin.cpp`
- `light_mappo-transformer/light_mappo-main/train/new.py`

资源与评估：

- `iSSROS/sensors.txt`
- `plugins/assess/AssessPlugin.cpp`
- `iSSROS/assessment.py`

#### 实验对比方法

基线：

- 原始 MAPPO：`obs0 + 固定 sensor mask`
- 随机策略
- 贪心策略：选择能力最高或能耗最低资源
- 可选：旧 MCTS/启发式能力匹配

实验场景：

- 同构 UAV 场景
- 异构 UAV 场景
- 资源离线场景
- 天气恶化导致 EO/IR 能力变化场景
- 不同任务类型比例场景

指标：

- 任务完成率
- 平均感知质量
- 平均能耗
- 无效动作率
- 资源利用率
- 平均回报
- 收敛速度

#### 可写成论文创新点的表述

提出一种面向异构 UAV 感知能力的资源属性增强 MAPPO 方法，将感知资源状态、环境退化后的动态能力评估和任务需求联合编码进状态空间，并通过动态动作掩码约束不可用资源选择，从而提高多 UAV 感知资源调度在异构和动态环境下的有效性与鲁棒性。

### 方案二：感知-计算协同的时延约束 MAPPO 调度方法

#### 方案名称

面向实时任务的 UAV 集群感知-计算协同调度 MAPPO 方法

#### 要解决的问题

当前代码只做感知资源选择，没有建模计算任务。论文题目中的计算负载、CPU 资源、边缘处理时延、本地处理时延、任务截止时间都没有进入状态、动作和奖励。

#### 核心技术

- 扩展任务模型：
  - 任务类型
  - 数据量 `data_size`
  - 计算量 `cpu_cycles`
  - deadline
  - priority
  - sensing_quality_requirement
- 扩展 UAV/edge 计算资源模型：
  - UAV 本地 CPU 频率
  - 边缘节点 CPU 频率
  - 当前队列长度
  - 剩余计算资源
  - 通信链路速率
- 扩展动作空间：
  - `[task_idx, sensor_idx, compute_node_idx]`
  - 或分层动作：先选任务，再选感知资源，再选计算位置
- 构建端到端时延模型：

```text
total_latency =
  sensing_time
  + transmission_time
  + queue_delay
  + compute_time
```

- 构建多目标奖励：

```text
reward =
  task_success_reward
  + priority_weight
  - latency_penalty
  - energy_penalty
  - deadline_violation_penalty
  - overload_penalty
```

#### 需要修改的文件

训练环境：

- `light_mappo-transformer/light_mappo-main/envs/env_core.py`
- `light_mappo-transformer/light_mappo-main/envs/env_discrete.py`
- `light_mappo-transformer/light_mappo-main/config.py`

MAPPO runner 和动作处理：

- `light_mappo-transformer/light_mappo-main/runner/separated/env_runner.py`
- `light_mappo-transformer/light_mappo-main/algorithms/algorithm/act.py`

在线 C++ 状态与调度：

- `iSSROS/core/ContextRenewManager.cpp`
- `iSSROS/core/CapNeedManager.cpp`
- `iSSROS/core/CapAdaptiveManager.cpp`
- `iSSROS/core/CapDispatchManager.cpp`

数据结构建议新增或扩展：

- `iSSROS/Cap/CapabilityNeed.*`
- `iSSROS/Resource/Resource.*`
- 可新增 `Task`、`ComputeResource`、`ComputeNode` 类

Python 推理接口：

- `plugins/select/selectPlugin.cpp`
- `light_mappo-transformer/light_mappo-main/train/new.py`

#### 实验对比方法

基线：

- 原始 MAPPO 只选传感器
- 最近边缘节点卸载
- 最小负载优先
- 最短处理时延优先
- 无计算卸载，仅本地计算

实验场景：

- 不同任务到达率
- 不同数据量和计算量
- UAV 本地算力不足
- 边缘节点拥塞
- 链路速率变化
- deadline 紧/松任务混合

指标：

- 任务完成率
- deadline 满足率
- 平均端到端时延
- 平均排队时延
- 平均能耗
- 计算资源利用率
- 边缘卸载比例
- 高优先级任务完成率

#### 可写成论文创新点的表述

提出一种面向 UAV 集群实时任务的感知-计算协同 MAPPO 调度方法，将感知资源选择、计算节点选择、通信传输时延和计算排队时延统一建模为多智能体强化学习问题，并通过时延约束奖励函数优化任务完成率、deadline 满足率和系统能耗。

### 方案三：面向可变规模任务与 UAV 的共享策略 MAPPO

#### 方案名称

面向可变规模 UAV 集群的共享策略与掩码增强 MAPPO 调度方法

#### 要解决的问题

当前训练环境和推理链路强依赖固定规模：

- 训练环境固定 `agent_num=2`
- 任务数固定为 5
- 观测维度固定为 15
- 权重目录是 `5UAVs`，但训练文档显示默认训练 2 个 agent
- C++ 按 `UAVid` 加载单独 actor，新增 UAV 需要额外权重

这会导致策略泛化弱，无法自然适应任务数量、资源数量和 UAV 数量变化。

#### 核心技术

- 使用参数共享 actor：
  - 所有 UAV 共用一个策略网络
  - UAV 个体差异通过资源特征、位置特征、负载特征输入
- 使用 padding + mask 表达可变任务数：
  - 最大任务数 `N_max`
  - 实际任务不足时 padding
  - padding 动作 mask 为 0
- 使用动态任务 mask 和资源 mask：
  - 已完成任务不可选
  - 被其他 UAV 占用的任务不可选
  - 不可用资源不可选
- 可选加入 attention pooling：
  - 对任务集合和资源集合做聚合编码
  - 提升不同规模下的泛化能力
- 在线侧改为加载共享 actor：
  - 不再为每个 `UAVid` 加载独立模型
  - `UAVid` 作为输入特征或仅用于读取当前 UAV 的资源状态

#### 需要修改的文件

训练环境：

- `light_mappo-transformer/light_mappo-main/envs/env_core.py`
- `light_mappo-transformer/light_mappo-main/envs/env_discrete.py`
- `light_mappo-transformer/light_mappo-main/config.py`

策略与 runner：

- `light_mappo-transformer/light_mappo-main/runner/separated/base_runner.py`
- `light_mappo-transformer/light_mappo-main/runner/separated/env_runner.py`
- `light_mappo-transformer/light_mappo-main/algorithms/algorithm/rMAPPOPolicy.py`
- 可选：`light_mappo-transformer/light_mappo-main/algorithms/algorithm/r_actor_critic.py`

在线推理：

- `light_mappo-transformer/light_mappo-main/train/new.py`
- `plugins/select/selectPlugin.cpp`
- `iSSROS/core/CapAdaptiveManager.cpp`

#### 实验对比方法

基线：

- 原始独立 actor MAPPO
- 固定 2 UAV 训练后直接测试 3/5 UAV
- 参数共享 MAPPO
- 参数共享 + 动态 mask MAPPO

训练测试设置：

- 训练：2 UAV、5 任务
- 测试：3 UAV、5 任务
- 测试：5 UAV、5 任务
- 测试：3 UAV、8 任务
- 测试：资源离线和任务数变化混合场景

指标：

- 不同 UAV 数量下的任务完成率
- 不同任务数量下的平均回报
- 训练收敛速度
- 模型参数量
- 新增 UAV 后无需重训性能
- 无效动作率
- 协同冲突率

#### 可写成论文创新点的表述

提出一种面向可变规模 UAV 集群任务调度的共享策略 MAPPO 方法，通过参数共享、任务/资源 padding 编码和动态动作掩码，使策略能够在不同 UAV 数量和任务数量场景下保持较好的泛化性能，降低多智能体策略训练与部署成本。

## 5. 推荐选题组合

如果时间有限，建议采用如下组合：

```text
主线：方案一
增强：deadline/priority + 简化计算时延
工程：Python 推理缓存和接口结构化
```

推荐论文题目可以写成：

```text
基于资源属性增强 MAPPO 的异构 UAV 集群感知与计算任务协同调度方法研究
```

建议章节组织：

1. 绪论：异构 UAV 感知与计算任务协同调度问题。
2. 系统建模：任务模型、感知资源模型、计算资源模型、约束和优化目标。
3. 资源属性增强 MAPPO 方法：状态、动作、动作掩码、奖励函数。
4. 感知-计算协同调度扩展：时延、能耗、deadline 和资源占用。
5. 系统实现：iS2ROS + MAPPO 插件链路、在线推理优化。
6. 实验评估：对比原始 MAPPO、启发式、随机策略，分析任务完成率、时延、能耗、资源利用率和泛化能力。

最稳妥的毕业设计落地路径：

```text
第 1 阶段：复现原始 MAPPO 训练和在线推理链路
第 2 阶段：把资源属性加入训练环境和在线输入
第 3 阶段：实现动态动作掩码和资源约束奖励
第 4 阶段：加入简化计算负载和 deadline
第 5 阶段：做对比实验和消融实验
```

## 6. 可验证指标汇总

建议最终实验至少包含以下指标：

| 指标 | 含义 | 对应论文价值 |
| --- | --- | --- |
| 任务完成率 | 完成任务数 / 总任务数 | 调度有效性 |
| deadline 满足率 | 按时完成任务数 / 总任务数 | 实时性 |
| 平均端到端时延 | 感知、传输、计算、等待总时延 | 感知-计算协同 |
| 平均能耗 | UAV 感知、计算、通信能耗 | 资源效率 |
| 感知质量得分 | 根据 EO/IR 能力和环境评估得到 | 感知资源质量 |
| 无效动作率 | 选择不可用任务/资源的比例 | 动作掩码有效性 |
| 资源冲突率 | 多任务争用同一资源的比例 | 约束满足能力 |
| 资源利用率 | 传感器和计算资源忙碌比例 | 资源调度效率 |
| 高优先级任务完成率 | 高 priority 任务完成比例 | 任务优先级建模 |
| 收敛速度 | 达到稳定回报所需训练步数 | 算法训练效率 |
| 推理时延 | C++ 到 Python actor 输出的耗时 | 在线部署实时性 |

## 7. 最终建议

最适合硕士毕设的方案是“方案一 + 方案二的简化版”。

原因：

- 与现有代码衔接最自然，能利用 `Capability`、`sensors.txt`、`AssessPlugin`、`MAPPO` 和 dispatch 链路。
- 论文贡献清晰：资源属性进入状态、动态 mask、感知-计算协同奖励。
- 实验指标容易设计，能和原始 MAPPO 形成明确对比。
- 工作量足够，但不至于完全推翻师兄代码。

不建议一开始就做完整 DAG 任务依赖或复杂图神经网络调度。这些方向论文价值高，但会显著增加训练环境、算法和实验复杂度，容易超出毕设周期。
