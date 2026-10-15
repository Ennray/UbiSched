from __future__ import annotations

"""根据 MatchMatrix 自动选择并执行最高分可行动作。"""

from dataclasses import dataclass
from typing import List

from ubisched.graph.match_matrix import MatchMatrix
from ubisched.scheduling.assignment_executor import AssignmentExecutor
from ubisched.scheduling.scheduling_state import AssignmentRecord, SchedulingState


@dataclass(frozen=True)
class SelectedAssignment:
    """规则调度器从匹配矩阵中选择的一个动作。"""

    subtask_id: str
    resource_id: str
    match_score: float
    subtask_index: int
    resource_index: int


@dataclass
class SchedulerRunResult:
    """一次自动调度运行的结果和基础评价指标。"""

    status: str
    start_time: float
    end_time: float
    iterations: int
    assignments: List[AssignmentRecord]
    total_energy: float
    deadline_met_rate: float
    unfinished_subtask_ids: List[str]

    @property
    def makespan(self) -> float:
        return self.end_time - self.start_time


class RuleBasedScheduler:
    """使用最高 match_score 策略运行完整任务图。"""

    def __init__(self, executor: AssignmentExecutor):
        self.executor = executor

    def select_assignment(
        self,
        match_matrix: MatchMatrix,
    ) -> SelectedAssignment | None:
        """选择分数最高的可行单资源分配，分数相同时保持矩阵顺序。"""
        selected: SelectedAssignment | None = None
        for task_index, row in enumerate(match_matrix.entries):
            for resource_index, entry in enumerate(row):
                if not entry.feasible:
                    continue
                if selected is not None and entry.match_score <= selected.match_score:
                    continue
                selected = SelectedAssignment(
                    subtask_id=match_matrix.subtask_ids[task_index],
                    resource_id=match_matrix.resource_ids[resource_index],
                    match_score=entry.match_score,
                    subtask_index=task_index,
                    resource_index=resource_index,
                )
        return selected

    def run(
        self,
        state: SchedulingState,
        max_iterations: int = 10_000,
    ) -> SchedulerRunResult:
        """自动分配并推进时间，直到全部完成或系统无法继续调度。"""
        if max_iterations <= 0:
            raise ValueError("max_iterations must be positive")

        start_time = state.now
        assignment_start = len(state.assignments)
        iterations = 0
        status = "completed"

        while not self._all_finished(state):
            if iterations >= max_iterations:
                status = "iteration_limit"
                break
            iterations += 1

            matrix = self.executor.build_match_matrix(state)
            selected = self.select_assignment(matrix)
            if selected is not None:
                self.executor.assign(
                    state,
                    selected.subtask_id,
                    selected.resource_id,
                )
                # 不立即推进时间，让其他空闲资源仍可接收独立的 ready 任务。
                continue

            if self.executor.next_event_time(state) is not None:
                self.executor.advance_to_next_event(state)
                continue

            # 没有可行动作且没有运行中的任务，说明硬约束使系统无法前进。
            status = "stalled"
            break

        new_assignments = state.assignments[assignment_start:]
        unfinished = [
            subtask.subtask_id
            for subtask in state.task_graph.subtasks
            if subtask.state != "finished"
        ]
        return SchedulerRunResult(
            status=status,
            start_time=start_time,
            end_time=state.now,
            iterations=iterations,
            assignments=new_assignments,
            total_energy=sum(
                assignment.estimated_energy for assignment in new_assignments
            ),
            deadline_met_rate=self._deadline_met_rate(state, new_assignments),
            unfinished_subtask_ids=unfinished,
        )

    @staticmethod
    def _all_finished(state: SchedulingState) -> bool:
        return all(
            subtask.state == "finished" for subtask in state.task_graph.subtasks
        )

    @staticmethod
    def _deadline_met_rate(
        state: SchedulingState,
        assignments: List[AssignmentRecord],
    ) -> float:
        completion_by_task = {
            assignment.subtask_id: assignment.completion_time
            for assignment in assignments
            if assignment.status == "finished"
        }
        completed_tasks = [
            subtask
            for subtask in state.task_graph.subtasks
            if subtask.subtask_id in completion_by_task
        ]
        if not completed_tasks:
            return 0.0
        met = sum(
            subtask.deadline <= 0
            or completion_by_task[subtask.subtask_id] <= subtask.deadline
            for subtask in completed_tasks
        )
        return met / len(completed_tasks)
