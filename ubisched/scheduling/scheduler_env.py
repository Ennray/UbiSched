from __future__ import annotations

"""UbiSched 的强化学习环境接口（第二阶段）。

这是**单次选择一个任务-资源组合**的离散事件环境，不是 MAPPO 多智能体环境。
其目的在于使规则/随机/学习策略使用相同的任务、资源、执行器与奖励定义。

接口借鉴 Gymnasium：reset() -> (observation, info)，
step(action_index) -> (observation, reward, terminated, truncated, info)。
本模块不依赖 gymnasium、numpy 或 torch。
"""

from copy import deepcopy
from dataclasses import dataclass
import math
from numbers import Integral
from typing import Any, Dict, List, Sequence, Mapping

from ubisched.graph.action_mask import ActionMaskBuilder
from ubisched.graph.match_matrix import RuleBasedScorer
from ubisched.graph.resource_graph import ResourceGraph
from ubisched.graph.task_graph import SubTask, TaskGraph
from ubisched.scheduling.assignment_executor import AssignmentExecutor
from ubisched.scheduling.scheduling_state import AssignmentRecord, SchedulingState


@dataclass(frozen=True)
class RewardConfig:
    """仿真奖励系数。完成奖励按结束事件发放，不能在分配时提前领取。"""

    completion: float = 1.0
    on_time_bonus: float = 0.25
    priority_bonus: float = 0.10
    quality_bonus: float = 0.20
    energy_cost: float = 0.10
    elapsed_time_cost: float = 0.02
    invalid_action: float = -0.5
    stalled: float = -1.0
    late_fixed_penalty: float = 0.0  # 第八阶段可选，完成晚于截止时间时扣除
    late_time_penalty: float = 0.0   # 每超期一秒的额外代价


class SchedulerEnv:
    """将已有的任务图、资源图、匹配矩阵和执行器组成可逐步交互的环境。

    action_index 从当前观察中的 action_labels 解释：按任务行、资源列展平，
    最后一项是 noop（等待下一事件）。运行时新增任务可能改变动作总数，
    后续接 MAPPO 时还需固定上限/padding 与逐 UAV 分组动作。
    """

    TASK_STATES = ("pending", "ready", "running", "finished", "failed")

    def __init__(
        self,
        task_graph: TaskGraph,
        resource_graph: ResourceGraph,
        scorer: RuleBasedScorer,
        *,
        max_steps: int = 1000,
        reward_config: RewardConfig | None = None,
    ) -> None:
        if max_steps <= 0:
            raise ValueError("max_steps must be positive")
        self._initial_tasks = deepcopy(task_graph)
        self._initial_resources = deepcopy(resource_graph)
        self.scorer = scorer
        self.executor = AssignmentExecutor(scorer)
        self._mask_builder = ActionMaskBuilder()
        self.rewards = reward_config or RewardConfig()
        self.max_steps = max_steps
        self.state: SchedulingState | None = None
        self.steps = 0
        self.terminated = False
        self.truncated = False
        self.status = "not_reset"
        self._resource_energy_scale = 1.0

    def reset(self, *, seed: int | None = None) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """独立重开一局，不修改初始化传入的图；本阶段无随机事件，seed 仅为兼容接口。"""
        del seed
        self.state = SchedulingState(
            task_graph=deepcopy(self._initial_tasks),
            resource_graph=deepcopy(self._initial_resources),
        )
        self._resource_energy_scale = max(
            1.0,
            *(resource.remaining_energy for resource in self.state.resource_graph.resources),
        )
        self.steps = 0
        self.terminated = self._all_finished()
        self.truncated = False
        self.status = "completed" if self.terminated else "running"
        return self.observe(), self._info(elapsed_time=0.0)

    def observe(self) -> Dict[str, Any]:
        """获取与环境内部可变状态不共享引用的数字特征和动作索引。"""
        state = self._require_reset()
        matrix = self.executor.build_match_matrix(state)
        mask = self._mask_builder.build(matrix)
        dependencies = self._unfinished_predecessors()

        task_features: List[List[float]] = []
        for task in state.task_graph.subtasks:
            deadline_remaining = (task.deadline - state.now) if task.deadline > 0 else 0.0
            state_flags = [float(task.state == name) for name in self.TASK_STATES]
            task_features.append([
                *state_flags,
                self._normalize(task.priority, "max_priority"),
                self._normalize(deadline_remaining, "max_latency"),
                self._normalize(max(0.0, task.arrival_time - state.now), "max_latency"),
                self._normalize(task.max_latency, "max_latency"),
                max(0.0, min(1.0, task.min_quality)),
                math.log1p(max(0.0, task.data_size)),
                math.log1p(max(0.0, task.compute_cycles)),
                float(task.task_type in {"detect", "track", "sense"}),
                float(task.task_type not in {"detect", "track", "sense"}),
                float(task.resource_count_min),
                float(dependencies.get(task.subtask_id, 0)),
            ])

        resource_features: List[List[float]] = []
        for resource in state.resource_graph.resources:
            resource_features.append([
                float(resource.resource_type == "sensor"),
                float(resource.resource_type == "compute"),
                float(resource.online),
                float(resource.occupied),
                max(0.0, resource.remaining_energy) / self._resource_energy_scale,
                self._normalize(resource.queue_length, "max_queue_length"),
                self._normalize(resource.cpu_frequency, "max_cpu_frequency"),
                math.log1p(max(0.0, resource.link_rate)),
                math.log1p(max(0.0, resource.power)),
                self._normalize(max(0.0, resource.release_time - state.now), "max_latency"),
                max(resource.sensing_quality.values(), default=0.0),
                *self._location3(resource.location),
            ])

        return {
            "time": state.now,
            "task_ids": list(matrix.subtask_ids),
            "resource_ids": list(matrix.resource_ids),
            "task_features": task_features,
            "resource_features": resource_features,
            "match_features": matrix.as_tensor(),
            "action_mask": list(mask.action_mask),
            "action_labels": list(mask.action_labels),
            "noop_index": mask.noop_index,
        }

    def step(
        self, action_index: int
    ) -> tuple[Dict[str, Any], float, bool, bool, Dict[str, Any]]:
        """选择当前观察的一个动作，并返回新的观察、奖励、终止和诊断信息。"""
        state = self._require_reset()
        if self.terminated or self.truncated:
            raise RuntimeError("Episode has ended; call reset() before step()")

        obs = self.observe()
        mask: List[int] = obs["action_mask"]
        n_resources = len(obs["resource_ids"])
        self.steps += 1
        reward = 0.0
        reward_parts: Dict[str, float] = {}
        completed: List[AssignmentRecord] = []
        started: AssignmentRecord | None = None
        reason = "assigned"
        elapsed = 0.0

        if (
            not isinstance(action_index, Integral)
            or isinstance(action_index, bool)
            or not 0 <= action_index < len(mask)
            or not mask[action_index]
        ):
            reason = "invalid_action"
            reward_parts["invalid_action"] = self.rewards.invalid_action
            reward += self.rewards.invalid_action
        elif action_index == obs["noop_index"]:
            next_time = self.executor.next_event_time(state)
            if next_time is not None:
                elapsed = next_time - state.now
                completed = self.executor.advance_time(state, next_time)
                reason = "wait_for_event"
            elif any(mask[:-1]):
                # 用户主动等待、但没有任何已知未来事件：时间不前进，避免伪造事件。
                reason = "no_future_event"
                reward_parts["invalid_wait"] = self.rewards.invalid_action
                reward += self.rewards.invalid_action
            else:
                # 全部剩余任务无法执行，也没有任何等待中的事件。
                reason = "stalled"
                self.terminated = True
                self.status = "stalled"
                reward_parts["stalled"] = self.rewards.stalled
                reward += self.rewards.stalled
        else:
            task_index, resource_index = divmod(action_index, n_resources)
            started = self.executor.assign(
                state, obs["task_ids"][task_index], obs["resource_ids"][resource_index]
            )
            # 处理允许零时延任务的情况，避免活跃任务永远无法结束。
            completed = self.executor.advance_time(state, state.now)
            energy_penalty = self.rewards.energy_cost * (
                started.estimated_energy / self._energy_normalization()
            )
            reward_parts["energy"] = -energy_penalty
            reward -= energy_penalty

        if elapsed > 0.0:
            wait_penalty = self.rewards.elapsed_time_cost * elapsed
            reward_parts["elapsed_time"] = -wait_penalty
            reward -= wait_penalty

        completion_reward = 0.0
        for item in completed:
            task = state.get_subtask(item.subtask_id)
            prio = self._normalize(task.priority, "max_priority")
            gain = (
                self.rewards.completion
                + self.rewards.priority_bonus * prio
                + self.rewards.quality_bonus * item.estimated_quality
            )
            if task.deadline > 0 and item.actual_end_time is not None:
                if item.actual_end_time <= task.deadline:
                    gain += self.rewards.on_time_bonus
            completion_reward += gain
        if completed:
            reward_parts["completion"] = completion_reward
            reward += completion_reward
            late_loss = 0.0
            for item in completed:
                task = state.get_subtask(item.subtask_id)
                if task.deadline > 0 and item.actual_end_time is not None:
                    overdue = max(0.0, item.actual_end_time - task.deadline)
                    if overdue > 0:
                        late_loss += (self.rewards.late_fixed_penalty
                                      + self.rewards.late_time_penalty * overdue)
            if late_loss:
                reward_parts["lateness"] = -late_loss
                reward -= late_loss

        if self._all_finished():
            self.terminated = True
            self.status = "completed"
        elif not self.terminated and self.steps >= self.max_steps:
            self.truncated = True
            self.status = "step_limit"

        info = self._info(elapsed_time=elapsed)
        info.update({
            "reason": reason,
            "started": None if started is None else (started.subtask_id, started.resource_id),
            "completed": [item.subtask_id for item in completed],
            "reward_parts": reward_parts,
        })
        return self.observe(), reward, self.terminated, self.truncated, info

    def add_subtask(self, subtask: SubTask, predecessors: Sequence[str] = (),
                    predecessor_data_sizes: Mapping[str, float] | None = None) -> None:
        """运行中注入新子任务。训练阶段的随机到达事件仍需后续单独建模。"""
        state = self._require_running()
        state.add_subtask(subtask, predecessors, predecessor_data_sizes)

    def set_link_online(self, source_uav_id: str, target_uav_id: str, online: bool) -> None:
        """运行期间注入 UAV 间通信故障/恢复事件。"""
        state = self._require_running()
        return self.executor.set_link_online(state, source_uav_id, target_uav_id, online)

    def fail_resource(
        self, resource_id: str, *, retry_task: bool = True
    ) -> List[AssignmentRecord]:
        """手动注入资源故障。不会自动推进到故障时刻，也不单独结算RL奖励。"""
        state = self._require_running()
        return self.executor.fail_resource(state, resource_id, retry_task=retry_task)

    def _info(self, *, elapsed_time: float) -> Dict[str, Any]:
        state = self._require_reset()
        total = len(state.task_graph.subtasks)
        finished = sum(t.state == "finished" for t in state.task_graph.subtasks)
        on_time_ids = {
            a.subtask_id
            for a in state.assignments
            if a.status == "finished"
            and (state.get_subtask(a.subtask_id).deadline <= 0
                 or (a.actual_end_time is not None
                     and a.actual_end_time <= state.get_subtask(a.subtask_id).deadline))
        }
        return {
            "status": self.status,
            "time": state.now,
            "steps": self.steps,
            "elapsed_time": elapsed_time,
            "finished_tasks": finished,
            "total_tasks": total,
            "completion_rate": finished / total if total else 1.0,
            "deadline_met_rate": len(on_time_ids) / total if total else 1.0,
            "total_energy": sum(a.estimated_energy for a in state.assignments),
        }

    def _unfinished_predecessors(self) -> Dict[str, int]:
        state = self._require_reset()
        result = {task.subtask_id: 0 for task in state.task_graph.subtasks}
        for edge in state.task_graph.edges:
            if state.get_subtask(edge.src_subtask_id).state != "finished":
                result[edge.dst_subtask_id] = result.get(edge.dst_subtask_id, 0) + 1
        return result

    def _normalize(self, value: float, key: str) -> float:
        scale = max(1e-9, float(self.scorer.normalization.get(key, 1.0)))
        return max(0.0, min(1.0, value / scale))

    def _energy_normalization(self) -> float:
        return max(1.0, float(self.scorer.normalization.get("max_energy", 1.0)))

    def _location3(self, coord: Sequence[float]) -> List[float]:
        scale = max(1e-9, float(self.scorer.normalization.get("max_distance", 1.0)))
        return [(float(coord[i]) if i < len(coord) else 0.0) / scale for i in range(3)]

    def _all_finished(self) -> bool:
        state = self._require_reset()
        return all(task.state == "finished" for task in state.task_graph.subtasks)

    def _require_reset(self) -> SchedulingState:
        if self.state is None:
            raise RuntimeError("Call reset() before using SchedulerEnv")
        return self.state

    def _require_running(self) -> SchedulingState:
        state = self._require_reset()
        if self.terminated or self.truncated:
            raise RuntimeError("Episode has ended; call reset() before modifying the state")
        return state
