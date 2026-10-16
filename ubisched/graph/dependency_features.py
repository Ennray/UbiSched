from __future__ import annotations

"""给学习策略使用的任务依赖图特征，不改变任务是否可执行的判断规则。

邻接矩阵 A[i][j]=1 表示任务 i 是任务 j 的直接前驱。
特征依次为：未完成直接后继比例、未完成全部后继比例、
下游最高优先级（归一化）、下游最紧迫的截止时间余量。
由当前任务图实时构造，因此运行时新增子任务后也可更新。
"""

from typing import List, Tuple

from ubisched.graph.task_graph import TaskGraph


def build_dependency_features(
    task_graph: TaskGraph, now: float, max_tasks: int
) -> Tuple[List[List[float]], List[List[float]]]:
    tasks = task_graph.subtasks
    n = len(tasks)
    if n > max_tasks or max_tasks < 1:
        raise ValueError("Task count exceeds configured max_tasks")
    ids = [task.subtask_id for task in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate subtask_id in task graph")
    index = {task_id: i for i, task_id in enumerate(ids)}
    adjacency: List[List[float]] = [[0.0] * max_tasks for _ in range(max_tasks)]
    children: List[set[int]] = [set() for _ in tasks]
    for edge in task_graph.edges:
        if edge.src_subtask_id not in index or edge.dst_subtask_id not in index:
            raise ValueError("Task edge references an unknown task")
        src, dst = index[edge.src_subtask_id], index[edge.dst_subtask_id]
        if src == dst:
            raise ValueError("Task dependency graph contains a cycle")
        children[src].add(dst)
        adjacency[src][dst] = 1.0

    # 计算所有后继，同时检查有向环，避免无效任务图静默进入神经网络。
    visited = [0] * n
    descendants: List[set[int]] = [set() for _ in tasks]

    def visit(i: int) -> set[int]:
        if visited[i] == 1:
            raise ValueError("Task dependency graph contains a cycle")
        if visited[i] == 2:
            return descendants[i]
        visited[i] = 1
        reachable: set[int] = set()
        for child in children[i]:
            reachable.add(child)
            reachable.update(visit(child))
        descendants[i] = reachable
        visited[i] = 2
        return reachable

    for i in range(n):
        visit(i)

    max_priority = max(1.0, *(max(0.0, t.priority) for t in tasks))
    features: List[List[float]] = []
    for i in range(n):
        unfinished = [tasks[j] for j in descendants[i] if tasks[j].state != "finished"]
        direct = sum(tasks[j].state != "finished" for j in children[i])
        earliest = min((t.deadline for t in unfinished if t.deadline > 0), default=0.0)
        # [-1,1]：负数表示下游任务已经逾期；没有下游期限则为0。
        slack = max(-1.0, min(1.0, (earliest - now) / 60.0)) if earliest else 0.0
        features.append([
            direct / max_tasks,
            len(unfinished) / max_tasks,
            max((t.priority for t in unfinished), default=0.0) / max_priority,
            slack,
        ])
    features.extend([[0.0] * 4 for _ in range(max_tasks - n)])
    return features, adjacency
