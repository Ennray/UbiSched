from __future__ import annotations

"""面向强化学习的关键路径估计特征（仅使用当前状态与已知任务图）。

这是忽略未来资源竞争的乐观估计，不是可执行调度的精确完工时间。
对每个节点输出 6 维：最短自身耗时、最长剩余路径耗时、
最紧路径截止时间余量、未完成后继比例、是否存在可用候选资源、自身余量。
路径估计以当前时刻为基准，忽略并行资源竞争和通信拓扑。
"""

from copy import copy
from math import isfinite
from typing import List

from ubisched.graph.match_matrix import RuleBasedScorer
from ubisched.scheduling.scheduling_state import SchedulingState


def _bounded(value: float, scale: float = 30.0) -> float:
    return max(-1.0, min(1.0, value / scale))


def build_critical_path_features(
    state: SchedulingState, scorer: RuleBasedScorer, max_tasks: int
) -> List[List[float]]:
    tasks = state.task_graph.subtasks
    n = len(tasks)
    if max_tasks < 1 or n > max_tasks:
        raise ValueError("Task count exceeds max_tasks")
    ids = {t.subtask_id: i for i, t in enumerate(tasks)}
    if len(ids) != n:
        raise ValueError("Duplicate subtask_id in task graph")
    children: list[set[int]] = [set() for _ in range(n)]
    for edge in state.task_graph.edges:
        if edge.src_subtask_id not in ids or edge.dst_subtask_id not in ids:
            raise ValueError("Task edge references an unknown task")
        children[ids[edge.src_subtask_id]].add(ids[edge.dst_subtask_id])

    durations: list[float] = []
    possible: list[float] = []
    for task in tasks:
        if task.state == "finished":
            durations.append(0.0)
            possible.append(1.0)
            continue
        if task.state == "running":
            active = [a for a in state.active_assignments() if a.subtask_id == task.subtask_id]
            if len(active) != 1:
                raise ValueError("Running task must have exactly one active assignment")
            durations.append(max(0.0, active[0].completion_time - state.now))
            possible.append(1.0)
            continue
        # 预测尚不可调度的任务时，暂时去除到达/前序/截止时间限制。
        # 仍检查资源类型、检测质量、位置、能量和单任务时延等物理约束。
        future_task = copy(task)
        future_task.state = "ready"
        future_task.arrival_time = 0.0
        future_task.deadline = 0.0
        candidates = []
        for resource in state.resource_graph.resources:
            if not resource.online:
                continue
            free = copy(resource)
            free.occupied = False
            free.release_time = state.now
            if scorer.score(future_task, free, state.now).feasible:
                candidates.append(scorer.estimate_execution(future_task, free, state.now).latency)
        possible.append(1.0 if candidates else 0.0)
        # 缺乏可用候选资源时保留保守哨兵值，由 possible=0 显式标识。
        durations.append(max(0.0, min(candidates)) if candidates else 120.0)

    status = [0] * n
    longest = [0.0] * n
    worst_slack: list[float | None] = [None] * n
    descendants: list[set[int]] = [set() for _ in range(n)]

    def visit(i: int) -> None:
        if status[i] == 1:
            raise ValueError("Task dependency graph contains a cycle")
        if status[i] == 2:
            return
        status[i] = 1
        local = durations[i]
        critical_length = local
        task = tasks[i]
        local_slack = (task.deadline - state.now - local
                       if task.deadline > 0 and task.state != "finished" else None)
        downstream: set[int] = set()
        for j in children[i]:
            visit(j)
            if tasks[j].state == "finished":
                continue
            downstream.add(j)
            downstream.update(descendants[j])
            critical_length = max(critical_length, local + longest[j])
            if worst_slack[j] is not None:
                downstream_slack = worst_slack[j] - local
                local_slack = (downstream_slack if local_slack is None
                               else min(local_slack, downstream_slack))
        longest[i] = critical_length
        worst_slack[i] = local_slack
        descendants[i] = downstream
        status[i] = 2

    for i in range(n):
        visit(i)

    features = []
    for i, task in enumerate(tasks):
        own_slack = (task.deadline - state.now - durations[i]
                     if task.deadline > 0 and task.state != "finished" else 0.0)
        features.append([
            min(1.0, durations[i] / 60.0),
            min(1.0, longest[i] / 60.0),
            _bounded(worst_slack[i]) if worst_slack[i] is not None else 0.0,
            len(descendants[i]) / max_tasks,
            possible[i],
            _bounded(own_slack),
        ])
    return features + [[0.0] * 6 for _ in range(max_tasks - n)]
