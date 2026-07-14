# UbiSched 第三阶段自动规则调度器说明

## 一、目标

前两个阶段已经能够计算任务资源匹配矩阵，并执行指定的 assign 动作。
第三阶段去掉 demo 中硬编码的任务和资源 ID，根据 MatchMatrix 自动完成任务图。

本阶段仍不接入 MAPPO，也不修改原 iS2ROS baseline、训练环境和奖励函数。

## 二、选择规则

`RuleBasedScheduler` 每轮执行：

1. 根据当前状态重新生成 MatchMatrix。
2. 在所有 `feasible = true` 的组合中选择 `match_score` 最高者。
3. 调用 `AssignmentExecutor.assign()` 执行分配。
4. 继续检查是否有其他空闲资源可以接收独立 ready 任务。
5. 没有可分配动作但存在运行任务时，推进到最近完成事件。
6. 任务完成后释放资源、解锁后继任务并重新匹配。
7. 所有任务完成后返回 `completed`。
8. 无可行动作且无运行任务时返回 `stalled`。

分数相同时保持 MatchMatrix 的行优先顺序，使结果可重复。

## 三、运行

```powershell
cd "F:\工作\173\代码\UbiSched"
python scripts/demo_rule_based_scheduling.py
```

示例任务图会自动产生：

```text
assign(detect_target, uav_1_rgb_sensor)
assign(classify_target, uav_2_compute)
```

输出指标包括：

- `status`：completed、stalled 或 iteration_limit。
- `makespan`：从调度开始到结束的总时间。
- `total_energy`：本次所有分配的预计总能耗。
- `deadline_met_rate`：已完成任务的 deadline 满足率。
- `unfinished_subtasks`：没有完成的子任务。

## 四、测试

```powershell
python -m pytest tests
```

新增测试覆盖最高分可行动作选择、完整任务图自动执行、指标统计、无可行资源
时的 stalled 状态以及迭代上限参数校验。

## 五、当前边界

- 当前策略是贪心最高分，不保证全局最优。
- resource_count_min/max 尚未进入多资源联合动作。
- 指标来自内部规则估算，不是 AirSim 实测数据。
- AirSim/iS2ROS UDP 通信尚未接入本调度器。
- 后续可以保持执行器不变，用 MAPPO 动作替换最高分选择规则。
