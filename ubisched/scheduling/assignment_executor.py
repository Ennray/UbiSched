from __future__ import annotations

"""执行分配动作并推进独立调度仿真的状态。"""

from typing import List

from ubisched.graph.action_mask import ActionMask, ActionMaskBuilder
from ubisched.graph.match_matrix import (
    MatchMatrix,
    MatchMatrixBuilder,
    RuleBasedScorer,
)
from ubisched.scheduling.scheduling_state import AssignmentRecord, SchedulingState


class AssignmentExecutor:
    """连接图匹配结果与任务、资源状态变化。"""

    def __init__(self, scorer: RuleBasedScorer):
        self.scorer = scorer
        self.matrix_builder = MatchMatrixBuilder(scorer)
        self.mask_builder = ActionMaskBuilder()

    def build_match_matrix(self, state: SchedulingState) -> MatchMatrix:
        """根据当前动态状态重新计算任务资源匹配矩阵。"""
        return self.matrix_builder.build(
            state.task_graph,
            state.resource_graph,
            current_time=state.now,
        )

    def build_action_mask(self, state: SchedulingState) -> ActionMask:
        """根据当前匹配矩阵重新生成动作掩码。"""
        return self.mask_builder.build(self.build_match_matrix(state))

    def assign(
        self,
        state: SchedulingState,
        subtask_id: str,
        resource_id: str,
    ) -> AssignmentRecord:
        """执行一个分配动作，并立即更新任务、资源和能量状态。

        执行前会使用当前时刻的数据重新评分，避免调用方使用已经过期的
        MatchMatrix 提交动作。
        """
        subtask = state.get_subtask(subtask_id)
        resource = state.get_resource(resource_id)
        match_entry = self.scorer.score(subtask, resource, state.now)
        if not match_entry.feasible:
            raise ValueError(
                f"Infeasible assignment: assign({subtask_id}, {resource_id})"
            )

        estimate = self.scorer.estimate_execution(subtask, resource, state.now)
        completion_time = state.now + estimate.latency
        record = AssignmentRecord(
            subtask_id=subtask_id,
            resource_id=resource_id,
            start_time=state.now,
            completion_time=completion_time,
            estimated_latency=estimate.latency,
            estimated_energy=estimate.energy,
        )

        subtask.state = "running"
        resource.occupied = True
        resource.release_time = completion_time
        resource.remaining_energy = max(
            0.0, resource.remaining_energy - estimate.energy
        )
        state.assignments.append(record)
        return record

    def advance_time(
        self,
        state: SchedulingState,
        new_time: float,
    ) -> List[AssignmentRecord]:
        """将仿真推进到 new_time，并完成所有在此之前结束的分配。"""
        if new_time < state.now:
            raise ValueError("new_time cannot be earlier than current_time")

        state.current_time = float(new_time)
        state.resource_graph.timestamp = state.now
        completed: List[AssignmentRecord] = []

        for assignment in state.active_assignments():
            if assignment.completion_time > state.now:
                continue

            subtask = state.get_subtask(assignment.subtask_id)
            resource = state.get_resource(assignment.resource_id)
            assignment.status = "finished"
            subtask.state = "finished"
            resource.occupied = False
            resource.release_time = assignment.completion_time
            completed.append(assignment)

        # 完成任务后立即解锁所有前序条件已经满足的后继任务。
        state.task_graph.update_ready_states()
        return completed

    def advance_to_next_event(
        self,
        state: SchedulingState,
    ) -> List[AssignmentRecord]:
        """推进到最近一次任务完成事件；没有运行任务时保持状态不变。"""
        active = state.active_assignments()
        if not active:
            return []
        next_completion = min(
            assignment.completion_time for assignment in active
        )
        return self.advance_time(state, next_completion)
