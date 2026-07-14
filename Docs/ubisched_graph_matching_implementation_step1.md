# UbiSched 第一阶段图匹配模块代码与测试说明

## 一、文档目的

本文说明 UbiSched 第一阶段图匹配模块的设计原理、代码结构、配置方式、任务资源匹配过程、动作掩码生成方式以及测试方法。

这一阶段实现的是一个可以独立运行的最小版本：

- 不接入 MAPPO。
- 不修改训练环境和奖励函数。
- 不修改原 iS2ROS baseline。
- 不引入 GNN 或其他深度学习模型。
- 不实现 ResourceEdge，通信能力暂时由 ResourceNode 的 `link_rate` 描述。
- 只使用可解释的规则完成任务与资源的匹配评分。

## 二、整体处理流程

模块的数据流如下：

```text
任务配置                         资源配置
   │                                │
   ▼                                ▼
TaskGraph                       ResourceGraph
   │                                │
   └───────────┬────────────────────┘
               ▼
       MatchMatrixBuilder
               │
               ▼
   N × M 个任务-资源匹配结果
               │
       ┌───────┴────────┐
       ▼                ▼
 feasible 矩阵      match_score 矩阵
       │
       ▼
 ActionMaskBuilder
       │
       ▼
assign(...) 动作掩码 + noop
```

其中，`N` 是子任务数量，`M` 是可执行资源数量。匹配矩阵第 `i` 行、第 `j` 列始终表示：

```text
subtask_ids[i] 与 resource_ids[j] 的匹配结果
```

## 三、代码和配置文件

核心代码：

| 文件 | 作用 |
| --- | --- |
| `ubisched/graph/task_graph.py` | 定义 SubTask、TaskEdge 和 TaskGraph，处理前序依赖与 ready 状态 |
| `ubisched/graph/resource_graph.py` | 定义 ResourceNode 和 ResourceGraph，描述异构资源状态 |
| `ubisched/graph/match_matrix.py` | 完成可行性判断、规则评分和匹配矩阵构建 |
| `ubisched/graph/action_mask.py` | 根据 feasible 矩阵生成动作掩码 |
| `scripts/demo_build_match_matrix.py` | 从示例配置运行完整构建流程 |

示例配置：

| 文件 | 作用 |
| --- | --- |
| `configs/ubisched/task_graph_example.yaml` | 定义示例任务图 |
| `configs/ubisched/resource_graph_example.yaml` | 定义示例资源图 |
| `configs/ubisched/match_scoring.yaml` | 定义归一化参数、基础时延、能耗参数和评分权重 |

测试代码：

| 文件 | 作用 |
| --- | --- |
| `tests/test_task_graph.py` | 测试任务图加载、前序状态更新和邻接矩阵 |
| `tests/test_resource_graph.py` | 测试资源图加载和资源类型限制 |
| `tests/test_match_matrix.py` | 测试匹配字段、模态语义和可行性判断 |
| `tests/test_action_mask.py` | 测试矩阵展平、动作标签和 noop |

## 四、任务图代码说明

### 4.1 SubTask

`SubTask` 是最小调度单元，主要字段如下：

| 字段 | 含义 |
| --- | --- |
| `subtask_id` | 子任务唯一标识 |
| `task_type` | 任务类型，例如 detect、track、classify |
| `priority` | 优先级 |
| `deadline` | 最晚完成时间 |
| `location` | 任务发生位置，支持二维或三维坐标 |
| `required_modalities_any` | 资源支持列表中的任意一种模态即可 |
| `min_quality` | 最低感知质量 |
| `data_size` | 待传输或处理的数据量 |
| `compute_cycles` | 所需计算周期数 |
| `max_latency` | 最大允许时延 |
| `resource_count_min/max` | 最少和最多资源数量约束 |
| `state` | pending、ready、running 或 finished 等状态 |

`required_modalities_any = ["rgb", "infrared"]` 的含义是：RGB 和红外中只要有一种满足要求即可。当前版本不是要求两种模态同时存在。

### 4.2 TaskEdge

第一阶段只支持 `precedence` 前序依赖。例如：

```text
detect_target ──precedence──> classify_target
```

这表示只有 `detect_target` 完成后，`classify_target` 才能从 `pending` 变为 `ready`。

### 4.3 ready 状态更新

`TaskGraph.update_ready_states()` 首先收集所有 `finished` 子任务，然后检查每个 `pending` 子任务的直接前序节点：

- 没有前序节点时，可以进入 `ready`。
- 所有前序节点都已经 `finished` 时，可以进入 `ready`。
- 只要还有一个前序未完成，就继续保持 `pending`。
- 方法不会覆盖 running、finished 等非 pending 状态。

`build_precedence_matrix()` 会生成任务邻接矩阵。示例任务图的结果为：

```text
[[0, 1],
 [0, 0]]
```

其中 `matrix[0][1] = 1` 表示第 0 个任务是第 1 个任务的前序。

## 五、资源图代码说明

### 5.1 ResourceNode

第一阶段只允许两种可执行资源：

- `sensor`：执行 detect、track、sense 感知任务。
- `compute`：执行当前规则中除上述感知任务外的计算任务。

UAV 本身不能作为动作资源。它只通过 `owner_uav_id` 表示传感器或计算节点属于哪架 UAV。

主要资源字段如下：

| 字段 | 含义 |
| --- | --- |
| `resource_id` | 资源唯一标识 |
| `resource_type` | sensor 或 compute |
| `owner_uav_id` | 所属 UAV |
| `location` | 当前资源位置 |
| `modalities` | 支持的感知模态 |
| `sensing_quality` | 每种模态对应的感知质量 |
| `detection_range` | 最大探测范围 |
| `power` | 工作功率 |
| `cpu_frequency` | CPU 频率 |
| `queue_length` | 当前排队长度 |
| `link_rate` | 当前链路速率 |
| `remaining_energy` | 剩余能量 |
| `occupied` | 是否被占用 |
| `release_time` | 预计释放时间 |

`ResourceNode.from_dict()` 会拒绝 `resource_type = "uav"`，确保动作始终分配到具体的传感器或计算资源，而不是笼统地分配给 UAV。

### 5.2 ResourceGraph

`ResourceGraph` 表示某个时间戳下所有资源的状态快照。第一阶段没有 ResourceEdge，因此资源之间的拓扑和链路关系尚未建模。

## 六、任务与资源如何匹配

### 6.1 两两组合

`MatchMatrixBuilder.build()` 会先刷新任务的 ready 状态，然后遍历所有组合：

```text
for 每个 SubTask:
    for 每个 ResourceNode:
        RuleBasedScorer.score(SubTask, ResourceNode)
```

每个组合生成一个 `MatchEntry`，包含：

```text
feasible
quality_score
latency_cost
energy_cost
distance_cost
load_cost
match_score
```

### 6.2 感知质量 quality_score

对于 sensor，代码检查资源支持的模态与 `required_modalities_any` 的交集，然后取命中模态中的最高质量：

```text
quality_score = max(命中模态的 sensing_quality)
```

例如任务需要 RGB 或红外，资源质量为：

```text
rgb      = 0.85
infrared = 0.78
```

则 `quality_score = 0.85`。

对于 compute，质量由 CPU 频率和队列负载共同估算：

```text
cpu_quality   = cpu_frequency / max_cpu_frequency
quality_score = clamp(cpu_quality × (1 - 0.5 × load_cost), 0, 1)
```

### 6.3 距离 distance_cost

首先计算任务位置与资源位置之间的欧氏距离：

```text
distance = sqrt((x1-x2)² + (y1-y2)² + (z1-z2)²)
```

然后使用配置中的 `max_distance` 归一化：

```text
distance_cost = clamp(distance / max_distance, 0, 1)
```

### 6.4 时延 latency_cost

总时延由四部分组成：

```text
等待时间 = max(0, release_time - current_time)
传输时间 = data_size / link_rate
计算时间 = compute_cycles / cpu_frequency
总时延   = 等待时间 + 传输时间 + 任务基础时间 + 计算时间
```

归一化后得到：

```text
latency_cost = clamp(总时延 / max_latency_normalization, 0, 1)
```

这里的 `max_latency_normalization` 来自评分配置，只用于归一化；SubTask 自身的 `max_latency` 是可行性硬约束，两者作用不同。

### 6.5 能耗 energy_cost

当前规则使用以下近似模型：

```text
energy = power × latency + data_size × energy_per_mb
energy_cost = clamp(energy / max_energy, 0, 1)
```

第一项表示资源工作期间的能耗，第二项表示随数据量增加的附加能耗。

### 6.6 负载 load_cost

```text
load_cost = clamp(queue_length / max_queue_length, 0, 1)
```

队列越长，负载代价越高。

## 七、可行性硬约束

`RuleBasedScorer._is_feasible()` 按以下条件判断一个任务资源组合能否形成有效动作：

1. 子任务必须是 `ready`。
2. 资源不能处于尚未释放的占用状态。
3. 资源剩余能量必须不小于预计能耗。
4. 预计时延不能超过子任务的 `max_latency`。
5. `current_time + latency` 不能超过 deadline。
6. 感知任务必须分配给 sensor。
7. 感知任务必须声明至少一种 `required_modalities_any`。
8. sensor 必须命中至少一种所需模态，并达到 `min_quality`。
9. 任务位置不能超出 sensor 的 `detection_range`。
10. 非感知任务必须分配给 CPU 频率大于 0 的 compute。

这些条件属于硬约束。任意一项不满足时：

```text
feasible = false
match_score = 0
```

当前第一版把 detect、track、sense 识别为感知任务，其他任务类型统一按计算任务处理。

## 八、综合匹配分数

只有 `feasible = true` 时才计算有效匹配分数：

```text
match_score =
    quality_weight  × quality_score
  - latency_weight  × latency_cost
  - energy_weight   × energy_cost
  - distance_weight × distance_cost
  - load_weight     × load_cost
  + priority_weight × priority_score
```

最终结果通过 `clamp` 限制在 `[0, 1]`。

质量和任务优先级是收益项；时延、能耗、距离和负载是代价项。权重来自 `configs/ubisched/match_scoring.yaml`，因此可以在不改代码的情况下调整调度偏好。

## 九、示例结果的计算含义

示例中有两个任务和两个资源：

```text
任务：
0 detect_target
1 classify_target

资源：
0 uav_1_rgb_sensor
1 uav_2_compute
```

因此 MatchMatrix 是 `2 × 2`。

`detect_target` 与 RGB 传感器匹配时：

```text
quality_score = max(0.85, 0.78) = 0.85
distance      = sqrt(10² + 5² + 20²) ≈ 22.9129
latency       = 20/10 + 1e9/1e9 + 2 = 5
energy        = 30×5 + 20×0.1 = 152
```

代入示例权重后：

```text
match_score ≈ 0.311992
```

最终输出：

```text
feasible matrix
[1, 0]
[0, 0]

match_score matrix
[0.3119920454858554, 0.0]
[0.0, 0.0]
```

解释如下：

- `[0][0] = 1`：detect_target 可以分配给 RGB 传感器。
- `[0][1] = 0`：compute 不能执行感知任务。
- 第二行均为 0：classify_target 仍是 pending，前序 detect_target 尚未完成。

## 十、动作掩码

`ActionMaskBuilder` 只读取 MatchMatrix 的 `feasible`，不重新判断任务或资源条件。

二维矩阵按行优先顺序展开。对于 `N` 个任务、`M` 个资源：

```text
assign 动作索引 = task_index × M + resource_index
noop 动作索引   = N × M
```

示例动作顺序为：

```text
0 assign(detect_target, uav_1_rgb_sensor)
1 assign(detect_target, uav_2_compute)
2 assign(classify_target, uav_1_rgb_sensor)
3 assign(classify_target, uav_2_compute)
4 noop
```

对应掩码：

```text
[1, 0, 0, 0, 1]
```

`1` 表示动作可选，`0` 表示动作被屏蔽。noop 始终保留，保证没有任何可行分配时动作集合仍然非空。

## 十一、如何运行 demo

在仓库根目录执行：

```powershell
cd "F:\工作\173\代码\UbiSched"
python scripts/demo_build_match_matrix.py
```

demo 会依次输出：

```text
TaskGraph summary
ResourceGraph summary
feasible matrix
match_score matrix
action_mask
```

当前示例输出的关键部分为：

```text
TaskGraph(id=mission_001, subtasks=2, edges=1, states={'ready': 1, 'pending': 1})
ResourceGraph(id=resources_t0, resources=2, types={'sensor': 1, 'compute': 1})
action_mask
[1, 0, 0, 0, 1]
```

## 十二、如何运行测试

在仓库根目录执行：

```powershell
python -m pytest tests
```

当前共运行 10 个测试，结果为：

```text
collected 10 items
10 passed
```

具体覆盖内容如下。

### 12.1 TaskGraph 测试

`tests/test_task_graph.py` 包含 3 个测试：

- 验证示例配置能够加载，任务 ID、节点顺序、边数量和 `required_modalities_any` 正确。
- 验证前序未完成时 classify_target 保持 pending，前序完成后变为 ready。
- 验证 precedence 邻接矩阵为 `[[0, 1], [0, 0]]`。

### 12.2 ResourceGraph 测试

`tests/test_resource_graph.py` 包含 2 个测试：

- 验证 sensor 和 compute 资源能够正确加载。
- 验证把 UAV 作为可执行资源时抛出 `ValueError`。

### 12.3 MatchMatrix 测试

`tests/test_match_matrix.py` 包含 4 个测试：

- 验证 MatchEntry 包含规定字段，所有归一化分数位于 `[0, 1]`。
- 验证 `required_modalities_any` 只需命中一种模态，并得到质量分数 0.85。
- 验证 pending 子任务对应的整行 feasible 都为 0。
- 验证 compute 不能执行 detect 感知任务。

### 12.4 ActionMask 测试

`tests/test_action_mask.py` 包含 1 个测试：

- 验证 feasible 矩阵按行优先展平为 `[1, 0, 0, 0]`。
- 验证末尾追加 noop 后得到 `[1, 0, 0, 0, 1]`。
- 验证第一个动作标签和 noop 标签、索引正确。

本次文档和源码注释整理后，重新运行测试的结果为 `10 passed`，demo 的矩阵和匹配分数与修改前一致。

## 十三、依赖和配置格式

示例配置文件采用 YAML 兼容的 JSON 写法。加载时：

1. 如果安装了 PyYAML，使用 `yaml.safe_load()`。
2. 如果没有安装 PyYAML，自动回退到标准库 `json.loads()`。

因此运行 demo 只需要 Python 标准库；运行测试需要安装 `pytest`。

## 十四、第一阶段边界

当前模块已经完成从数据配置到任务图、资源图、匹配矩阵和动作掩码的独立闭环，但仍有以下边界：

- `resource_count_min` 和 `resource_count_max` 已进入数据结构，尚未用于多资源联合分配。
- 暂无 `required_modalities_all`。
- 暂无 ResourceEdge 和显式通信拓扑。
- 规则评分参数需要后续结合仿真单位和场景数据标定。
- 尚未把 MatchMatrix 接入 MAPPO 的状态、动作和奖励。
- 当前动作掩码只表示单个 `assign(subtask_id, resource_id)` 是否可选，不负责执行分配或更新资源状态。
