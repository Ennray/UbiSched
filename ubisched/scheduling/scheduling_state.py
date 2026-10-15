from __future__ import annotations

"""动态调度过程中的任务、资源、时间和分配记录。"""

from dataclasses import dataclass, field
from typing import List, Sequence

from ubisched.graph.resource_graph import ResourceGraph, ResourceNode
from ubisched.graph.task_graph import SubTask, TaskGraph


@dataclass
class AssignmentRecord:
    """一次已经开始执行的 assign(subtask_id, resource_id) 动作。"""

    subtask_id: str
    resource_id: str
    start_time: float
    completion_time: float
    estimated_latency: float
    estimated_energy: float
    estimated_quality: float = 0.0
    status: str = "running"
    actual_end_time: float | None = None
    failure_reason: str | None = None


@dataclass
class SchedulingState:
    """保存独立调度循环在某一时刻的完整可变状态。"""

    task_graph: TaskGraph
    resource_graph: ResourceGraph
    current_time: float | None = None
    assignments: List[AssignmentRecord] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.current_time is None:
            self.current_time = self.resource_graph.timestamp
        if self.current_time < 0:
            raise ValueError("current_time must be non-negative")
        self.resource_graph.timestamp = self.current_time
        self.task_graph.update_ready_states(float(self.current_time))

    @property
    def now(self) -> float:
        """返回确定为 float 的当前仿真时间。"""
        return float(self.current_time)

    def get_resource(self, resource_id: str) -> ResourceNode:
        for resource in self.resource_graph.resources:
            if resource.resource_id == resource_id:
                return resource
        raise KeyError(f"Unknown resource_id: {resource_id}")

    def get_subtask(self, subtask_id: str) -> SubTask:
        return self.task_graph.get_subtask(subtask_id)

    def active_assignments(self) -> List[AssignmentRecord]:
        return [
            assignment
            for assignment in self.assignments
            if assignment.status == "running"
        ]

    def add_subtask(self, subtask: SubTask, predecessors: Sequence[str] = ()) -> None:
        """仿真运行期间增加子任务并更新就绪状态。"""
        self.task_graph.add_subtask(subtask, predecessors)
        self.task_graph.update_ready_states(self.now)

    def summary(self) -> str:
        running = len(self.active_assignments())
        finished = sum(
            assignment.status == "finished" for assignment in self.assignments
        )
        return (
            f"SchedulingState(time={self.now}, "
            f"running_assignments={running}, finished_assignments={finished})"
        )
