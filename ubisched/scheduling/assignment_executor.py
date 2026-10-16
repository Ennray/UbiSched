from __future__ import annotations

"""执行分配动作并推进独立调度仿真的状态。"""

from typing import List

from ubisched.graph.action_mask import ActionMask, ActionMaskBuilder
from ubisched.graph.data_transfer import estimate_data_transfer
from ubisched.graph.match_matrix import (
    MatchMatrix,
    MatchMatrixBuilder,
    RuleBasedScorer,
)
from ubisched.scheduling.scheduling_state import AssignmentRecord, SchedulingState, TransferReservation


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
            state=state,
        )

    def score_assignment(self, state: SchedulingState, subtask_id: str, resource_id: str):
        task = state.get_subtask(subtask_id)
        resource = state.get_resource(resource_id)
        transfer = estimate_data_transfer(state, subtask_id, resource_id)
        return self.scorer.score(task, resource, state.now, transfer)

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
        transfer = estimate_data_transfer(state, subtask_id, resource_id)
        match_entry = self.scorer.score(subtask, resource, state.now, transfer)
        if not match_entry.feasible:
            raise ValueError(
                f"Infeasible assignment: assign({subtask_id}, {resource_id})"
            )

        estimate = self.scorer.estimate_execution(subtask, resource, state.now, transfer)
        completion_time = state.now + estimate.latency
        record = AssignmentRecord(
            subtask_id=subtask_id,
            resource_id=resource_id,
            start_time=state.now,
            completion_time=completion_time,
            estimated_latency=estimate.latency,
            estimated_energy=estimate.energy,
            estimated_quality=match_entry.quality_score,
            communication_latency=transfer.latency,
            communication_energy=transfer.energy,
            communication_hops=list(transfer.hops),
            communication_queue_wait=transfer.queue_wait_s,
            compute_start_time=state.now + transfer.latency,
        )

        subtask.state = "running"
        resource.occupied = True
        resource.release_time = completion_time
        # 本地执行能耗扣执行资源，通信发送能耗扣源资源。
        # 与 estimated_energy 的合计保持一致，避免重复扣费。
        resource.remaining_energy = max(
            0.0, resource.remaining_energy - (estimate.energy - transfer.energy)
        )
        for source_id, cost in transfer.source_energy_debits.items():
            source_resource = state.get_resource(source_id)
            source_resource.remaining_energy = max(0.0, source_resource.remaining_energy - cost)
        # 只有分配成功才真正占用链路时段；匹配和观测不产生副作用。
        for hop in transfer.hops:
            state.transfer_reservations.append(TransferReservation(
                subtask_id=subtask_id, resource_id=resource_id,
                source_resource_id=hop.source_resource_id,
                source_uav_id=hop.source_uav_id,
                target_uav_id=hop.target_uav_id,
                start_time=hop.start_time, end_time=hop.end_time,
                data_size_mb=hop.data_size_mb, energy=hop.energy,
                status=('transferring' if hop.start_time <= state.now else 'queued'),
            ))
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
        for transfer in state.transfer_reservations:
            if transfer.status == "cancelled":
                continue
            if transfer.end_time <= state.now + 1e-9:
                transfer.status = "finished"
            elif transfer.start_time <= state.now + 1e-9:
                transfer.status = "transferring"
            else:
                transfer.status = "queued"
        completed: List[AssignmentRecord] = []

        for assignment in state.active_assignments():
            if assignment.completion_time > state.now:
                continue

            subtask = state.get_subtask(assignment.subtask_id)
            resource = state.get_resource(assignment.resource_id)
            assignment.status = "finished"
            assignment.actual_end_time = assignment.completion_time
            subtask.state = "finished"
            resource.occupied = False
            resource.release_time = assignment.completion_time
            completed.append(assignment)

        # 完成任务后立即解锁所有前序条件已经满足的后继任务。
        state.task_graph.update_ready_states(state.now)
        return completed

    def fail_resource(
        self,
        state: SchedulingState,
        resource_id: str,
        *,
        retry_task: bool = True,
        reason: str = "resource_offline",
    ) -> List[AssignmentRecord]:
        """处理资源掉线：中断运行任务，必要时重新排队等待调度。

        在调用前先 advance_time() 到故障时刻。已预扣的估算能耗不返还，
        避免把失败执行当作完全没有成本。实际能耗将在执行反馈模块接入后计算。
        """
        resource = state.get_resource(resource_id)
        resource.online = False
        interrupted: List[AssignmentRecord] = []
        for assignment in state.active_assignments():
            if assignment.resource_id != resource_id:
                continue
            assignment.status = "failed"
            assignment.actual_end_time = state.now
            assignment.failure_reason = reason
            self._cancel_transfers(state, assignment.subtask_id, assignment.resource_id)
            subtask = state.get_subtask(assignment.subtask_id)
            subtask.state = "pending" if retry_task else "failed"
            interrupted.append(assignment)
        resource.occupied = False
        resource.release_time = state.now
        state.task_graph.update_ready_states(state.now)
        return interrupted

    @staticmethod
    def _cancel_transfers(state: SchedulingState, subtask_id: str,
                          resource_id: str) -> None:
        for transfer in state.transfer_reservations:
            if (transfer.subtask_id == subtask_id
                and transfer.resource_id == resource_id
                and transfer.status not in {"finished", "cancelled"}):
                transfer.status = "cancelled"

    def set_link_online(self, state: SchedulingState, source_uav_id: str,
                        target_uav_id: str, online: bool,
                        *, retry_task: bool = True) -> List[AssignmentRecord]:
        """断链中断未传完的任务；已结束传输的计算任务继续运行。"""
        state.resource_graph.set_link_online(source_uav_id, target_uav_id, online)
        if online:
            return []
        affected = {(r.subtask_id, r.resource_id)
                    for r in state.transfer_reservations
                    if r.source_uav_id == source_uav_id
                    and r.target_uav_id == target_uav_id
                    and r.end_time > state.now + 1e-9
                    and r.status != "cancelled"}
        interrupted = []
        for assignment in state.active_assignments():
            if (assignment.subtask_id, assignment.resource_id) not in affected:
                continue
            assignment.status = "failed"
            assignment.actual_end_time = state.now
            assignment.failure_reason = "link_offline"
            self._cancel_transfers(state, assignment.subtask_id, assignment.resource_id)
            resource = state.get_resource(assignment.resource_id)
            resource.occupied = False
            resource.release_time = state.now
            subtask = state.get_subtask(assignment.subtask_id)
            subtask.state = "pending" if retry_task else "failed"
            interrupted.append(assignment)
        state.task_graph.update_ready_states(state.now)
        return interrupted

    def restore_resource(self, state: SchedulingState, resource_id: str) -> None:
        """使掉线资源重新参与匹配，不能自动恢复中断任务。"""
        state.get_resource(resource_id).online = True

    def next_event_time(self, state: SchedulingState) -> float | None:
        """获取最近的任务完成或待到达任务的时刻。"""
        future = [
            assignment.completion_time
            for assignment in state.active_assignments()
            if assignment.completion_time > state.now
        ]
        future.extend(
            task.arrival_time
            for task in state.task_graph.subtasks
            if task.state in {"pending", "ready"} and task.arrival_time > state.now
        )
        return min(future) if future else None

    def next_communication_event_time(self, state: SchedulingState) -> float | None:
        """仅返回最近的传输开始或完成事件，不改变旧调度循环的事件语义。"""
        future = []
        for transfer in state.transfer_reservations:
            if transfer.status in {"cancelled", "finished"}:
                continue
            if transfer.start_time > state.now + 1e-9:
                future.append(transfer.start_time)
            if transfer.end_time > state.now + 1e-9:
                future.append(transfer.end_time)
        return min(future) if future else None

    def advance_to_next_event(
        self,
        state: SchedulingState,
    ) -> List[AssignmentRecord]:
        """推进到最近任务完成或新任务到达的时间点。"""
        next_time = self.next_event_time(state)
        if next_time is None:
            return []
        return self.advance_time(state, next_time)
