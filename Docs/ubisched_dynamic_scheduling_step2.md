# UbiSched 第二阶段动态调度闭环实现说明

## 一、实现目标

第一阶段解决“一个子任务能否分配给一个资源，以及匹配程度如何”的问题。
第二阶段解决“执行分配动作后，任务和资源状态如何随时间变化”的问题。

本阶段仍然是独立模块：

- 不接入 MAPPO。
- 不修改训练环境和奖励函数。
- 不修改原 iS2ROS baseline。
- 不实现 ResourceEdge。
- 不引入 GNN 或其他深度学习模型。

## 二、新增文件

```text
ubisched/scheduling/__init__.py
ubisched/scheduling/scheduling_state.py
ubisched/scheduling/assignment_executor.py
scripts/demo_dynamic_scheduling.py
tests/test_dynamic_scheduling.py
```

`ubisched/graph/match_matrix.py` 新增了公开的
`estimate_execution()`，让匹配阶段与执行阶段复用同一套时延和能耗公式。

## 三、动态调度流程

```text
SchedulingState
      │
      ▼
重新生成 MatchMatrix 和 ActionMask
      │
      ▼
assign(subtask_id, resource_id)
      │
      ├── SubTask: ready → running
      ├── ResourceNode: occupied = true
      ├── 设置 release_time
      ├── 扣除 remaining_energy
      └── 保存 AssignmentRecord
      │
      ▼
advance_time() 或 advance_to_next_event()
      │
      ├── SubTask: running → finished
      ├── ResourceNode: occupied = false
      └── 后继 SubTask: pending → ready
      │
      ▼
重新生成下一时刻的 MatchMatrix 和 ActionMask
```

## 四、核心数据结构

### 4.1 SchedulingState

`SchedulingState` 保存：

- 当前 `TaskGraph`。
- 当前 `ResourceGraph`。
- 当前仿真时间 `current_time`。
- 所有分配记录 `assignments`。

资源图的 `timestamp` 会与当前仿真时间保持一致。

### 4.2 AssignmentRecord

每次成功分配会生成一条记录：

| 字段 | 含义 |
| --- | --- |
| `subtask_id` | 被分配的子任务 |
| `resource_id` | 执行该任务的资源 |
| `start_time` | 开始时间 |
| `completion_time` | 预计完成时间 |
| `estimated_latency` | 预计执行时延 |
| `estimated_energy` | 预计消耗能量 |
| `status` | running 或 finished |

## 五、AssignmentExecutor

### 5.1 assign()

`assign()` 不直接相信旧 MatchMatrix，而是使用当前状态重新评分。这样可以防止
资源状态变化后仍执行过期动作。

不可行分配会抛出 `ValueError`，且不会改变状态。

成功分配后：

```text
subtask.state = "running"
resource.occupied = true
resource.release_time = current_time + estimated_latency
resource.remaining_energy -= estimated_energy
```

### 5.2 advance_time()

`advance_time(state, new_time)` 将仿真推进到指定时刻：

- 禁止时间倒退。
- 完成所有 `completion_time <= new_time` 的运行任务。
- 释放这些任务占用的资源。
- 更新任务前序关系，解锁满足条件的后继任务。

### 5.3 advance_to_next_event()

该方法自动寻找最近的任务完成时间并推进到该时刻。没有运行任务时保持状态不变。

### 5.4 重新匹配

```python
matrix = executor.build_match_matrix(state)
mask = executor.build_action_mask(state)
```

这两个方法始终使用当前任务、资源和仿真时间重新计算结果。

## 六、运行动态 demo

在仓库根目录执行：

```powershell
cd "F:\工作\173\代码\UbiSched"
python scripts/demo_dynamic_scheduling.py
```

demo 执行以下过程：

1. 将 `detect_target` 分配给 RGB 传感器。
2. 传感器变为占用，任务变为 running，能量从 5000 降为 4848。
3. 时间推进到 5.0，感知任务完成并释放传感器。
4. `classify_target` 从 pending 变为 ready。
5. 新 MatchMatrix 变为 `[[0, 0], [0, 1]]`。
6. 将分类任务分配给计算资源。
7. 时间推进到 9.25，两个任务全部完成。
8. 最终动作掩码只保留 noop：`[0, 0, 0, 0, 1]`。

## 七、运行测试

```powershell
python -m pytest tests
```

当前共 17 项测试：

- 第一阶段图匹配测试 10 项。
- 第二阶段动态调度测试 7 项。

新增测试覆盖：

- 成功分配后的任务、资源、能量和记录更新。
- 不可行分配被拒绝且状态不变。
- 未到完成时间时任务继续运行。
- 到达完成时间后释放资源并解锁后继任务。
- 状态变化后重新构建 MatchMatrix。
- 两阶段任务图完整执行。
- 禁止仿真时间倒退。

验证结果：

```text
17 passed
```

## 八、当前边界

- 一个 assign 动作仍然只分配一个资源，尚未执行 `resource_count_min/max`。
- 当前在任务开始时一次性扣除预计能量。
- 尚未根据任务执行动态更新 queue_length。
- noop 仍是动作掩码中的保底动作；时间推进由执行器显式调用。
- 尚未实现任务失败、中断、取消和重新调度。
- 尚未接入 MAPPO。
