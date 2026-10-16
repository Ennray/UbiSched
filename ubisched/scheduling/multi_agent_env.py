from __future__ import annotations

"""第三阶段：以 UAV 为智能体的集中执行、多智能体协作环境。

- 每个 UAV 只选择自己拥有的具体传感器/计算节点；动作是 (task_slot, resource_slot)。
- 所有 UAV 在同一仿真时刻提出动作；统一执行器依次核验并预约资源。
- Actor 使用局部观测，训练期 Critic 可通过 state_vector() 获取全局状态。
- 固定 max_tasks/max_resources_per_uav/max_agents 后观测和动作维度固定。
- 该环境不依赖 torch。时间推进是离散事件式的，仍使用估计时延。
"""

from copy import deepcopy
from numbers import Integral
from typing import Any, Dict, List, Mapping

from ubisched.graph.dependency_features import build_dependency_features
from ubisched.graph.critical_path import build_critical_path_features
from ubisched.graph.match_matrix import RuleBasedScorer
from ubisched.graph.resource_graph import ResourceGraph
from ubisched.graph.task_graph import TaskGraph
from ubisched.scheduling.scheduler_env import RewardConfig, SchedulerEnv
from ubisched.scheduling.scheduling_state import AssignmentRecord


class MultiAgentSchedulerEnv:
    """参数共享的多 UAV 调度实验环境。奖励为全体 UAV 共用的团队奖励。"""

    def __init__(
        self,
        task_graph: TaskGraph,
        resource_graph: ResourceGraph,
        scorer: RuleBasedScorer,
        *,
        max_tasks: int = 16,
        max_resources_per_uav: int = 4,
        max_agents: int = 8,
        max_steps: int = 1000,
        reward_config: RewardConfig | None = None,
        include_deadline_features: bool = False,
        include_dependency_features: bool = False,
        include_critical_path_features: bool = False,
    ) -> None:
        if min(max_tasks, max_resources_per_uav, max_agents) <= 0:
            raise ValueError("All capacity limits must be positive")
        self.max_tasks = max_tasks
        self.include_deadline_features = include_deadline_features
        self.include_dependency_features = include_dependency_features
        self.include_critical_path_features = include_critical_path_features
        if include_critical_path_features and not include_dependency_features:
            raise ValueError("Critical path features require dependency features")
        self.max_resources_per_uav = max_resources_per_uav
        self.max_agents = max_agents
        self._base = SchedulerEnv(
            task_graph, resource_graph, scorer,
            max_steps=max_steps, reward_config=reward_config,
        )
        owners: Dict[str, List[str]] = {}
        seen_resources: set[str] = set()
        for resource in resource_graph.resources:
            if not resource.owner_uav_id:
                raise ValueError(f"Resource {resource.resource_id} has no owner_uav_id")
            if resource.resource_id in seen_resources:
                raise ValueError(f"Duplicate resource_id: {resource.resource_id}")
            seen_resources.add(resource.resource_id)
            owners.setdefault(resource.owner_uav_id, []).append(resource.resource_id)
        self.agents = tuple(sorted(owners))
        if not self.agents:
            raise ValueError("Expected at least one UAV with executable resources")
        if len(self.agents) > max_agents:
            raise ValueError("UAV count exceeds max_agents")
        self.resource_ids_by_agent = {
            owner: tuple(sorted(resource_ids)) for owner, resource_ids in owners.items()
        }
        if any(len(ids) > max_resources_per_uav for ids in self.resource_ids_by_agent.values()):
            raise ValueError("Resource count exceeds max_resources_per_uav")
        if len(task_graph.subtasks) > max_tasks:
            raise ValueError("Task count exceeds max_tasks")
        self.noop_index = max_tasks * max_resources_per_uav
        self.action_dim = self.noop_index + 1
        self._task_feature_dim = 0
        self._resource_feature_dim = 0
        self._match_feature_dim = 7
        self._last_conflicts = 0

    @property
    def state(self):
        return self._base.state

    @property
    def executor(self):
        return self._base.executor

    def reset(self, *, seed: int | None = None):
        raw, info = self._base.reset(seed=seed)
        self._task_feature_dim = len(raw["task_features"][0]) if raw["task_features"] else 17
        self._resource_feature_dim = len(raw["resource_features"][0]) if raw["resource_features"] else 14
        self._last_conflicts = 0
        return self.observe(), self._info(info)

    def observe(self) -> Dict[str, Dict[str, Any]]:
        """字典按 UAV id 索引。局部观测不含其他 UAV 的资源特征。"""
        raw = self._base.observe()
        self._validate_capacities(raw)
        task_ids = raw["task_ids"]
        resource_index = {resource_id: i for i, resource_id in enumerate(raw["resource_ids"])}
        n_resources = len(raw["resource_ids"])
        task_features = self._pad(raw["task_features"], self.max_tasks, self._task_feature_dim)
        task_valid = [1] * len(task_ids) + [0] * (self.max_tasks - len(task_ids))
        if self.include_dependency_features:
            dependency_features, dependency_matrix = build_dependency_features(
                self.state.task_graph, self.state.now, self.max_tasks
            )
        else:
            dependency_features, dependency_matrix = None, None
        critical_features = (build_critical_path_features(
            self.state, self._base.scorer, self.max_tasks
        ) if self.include_critical_path_features else None)
        out: Dict[str, Dict[str, Any]] = {}
        for agent_index, agent in enumerate(self.agents):
            own_ids = self.resource_ids_by_agent[agent]
            own_indices = [resource_index[resource_id] for resource_id in own_ids]
            resources = [raw["resource_features"][idx] for idx in own_indices]
            pair_features = [
                [raw["match_features"][ti][ri] for ri in own_indices]
                for ti in range(len(task_ids))
            ]
            pair_features = [
                row + [[0.0] * self._match_feature_dim for _ in range(self.max_resources_per_uav - len(own_ids))]
                for row in pair_features
            ]
            pair_features += [
                [[0.0] * self._match_feature_dim for _ in range(self.max_resources_per_uav)]
                for _ in range(self.max_tasks - len(task_ids))
            ]
            action_mask = [0] * self.action_dim
            labels: List[tuple[str, str] | None] = [None] * self.action_dim
            for ti, task_id in enumerate(task_ids):
                for ri, resource_id in enumerate(own_ids):
                    action = ti * self.max_resources_per_uav + ri
                    labels[action] = (task_id, resource_id)
                    action_mask[action] = int(raw["action_mask"][ti * n_resources + own_indices[ri]])
            action_mask[self.noop_index] = 1
            # 匹配剩余时间裕量：deadline - (now + estimated_latency)。
            # 仅对可执行动作提供 [0,1] 的紧迫程度，越靠近截止时间越接近 1。
            # 不改变匹配约束和基础 MatchEntry 的七个字段。
            urgency = [0.0] * (self.max_tasks * self.max_resources_per_uav)
            if self.include_deadline_features:
                for ai, label in enumerate(labels[:-1]):
                    if label is None or not action_mask[ai]:
                        continue
                    task = self.state.get_subtask(label[0])
                    if task.deadline <= 0:
                        continue
                    resource = self.state.get_resource(label[1])
                    from ubisched.graph.data_transfer import estimate_data_transfer
                    transfer = estimate_data_transfer(self.state, task.subtask_id, resource.resource_id)
                    estimate = self._base.scorer.estimate_execution(task, resource, self.state.now, transfer)
                    slack = task.deadline - self.state.now - estimate.latency
                    urgency[ai] = max(0.0, min(1.0, 1.0 - slack / 20.0))
            out[agent] = {
                "agent_id": agent,
                "agent_index": agent_index,
                "time": raw["time"],
                "task_ids": list(task_ids),
                "resource_ids": list(own_ids),
                "task_features": deepcopy(task_features),
                "task_valid": list(task_valid),
                "resource_features": self._pad(resources, self.max_resources_per_uav, self._resource_feature_dim),
                "resource_valid": [1] * len(own_ids) + [0] * (self.max_resources_per_uav - len(own_ids)),
                "match_features": pair_features,
                "action_mask": action_mask,
                "action_labels": labels,
                "noop_index": self.noop_index,
                "urgency_features": urgency,
                **({"dependency_features": deepcopy(dependency_features),
                    "dependency_matrix": deepcopy(dependency_matrix)}
                   if self.include_dependency_features else {}),
                **({"critical_path_features": deepcopy(critical_features)}
                   if self.include_critical_path_features else {}),
            }
        return out

    def local_vector(self, observation: Mapping[str, Any]) -> List[float]:
        """训练 Actor 用的定长扁平特征；不包括非法动作掩码。"""
        return (
            [float(observation["agent_index"]) / max(1, self.max_agents - 1)]
            + [float(v) for row in observation["task_features"] for v in row]
            + [float(v) for row in observation["resource_features"] for v in row]
            + [float(v) for group in observation["match_features"] for row in group for v in row]
            + [float(observation["time"]) / 1000.0]
            + ([float(v) for v in observation["urgency_features"]]
               if self.include_deadline_features else [])
        )

    def state_vector(self) -> List[float]:
        """只给集中式 Critic 使用，包含全体 UAV 的资源信息。"""
        raw = self._base.observe()
        self._validate_capacities(raw)
        tasks = self._pad(raw["task_features"], self.max_tasks, self._task_feature_dim)
        resource_index = {rid: idx for idx, rid in enumerate(raw["resource_ids"])}
        resources: List[List[float]] = []
        matches: List[List[List[float]]] = []
        for agent in self.agents:
            ids = self.resource_ids_by_agent[agent]
            indices = [resource_index[rid] for rid in ids]
            resources.extend(self._pad(
                [raw["resource_features"][i] for i in indices],
                self.max_resources_per_uav, self._resource_feature_dim
            ))
            for ti in range(self.max_tasks):
                vals = [raw["match_features"][ti][i] for i in indices] if ti < len(raw["task_ids"]) else []
                matches.append(self._pad(vals, self.max_resources_per_uav, self._match_feature_dim))
        missing_agents = self.max_agents - len(self.agents)
        resources += [[0.0] * self._resource_feature_dim for _ in range(missing_agents * self.max_resources_per_uav)]
        matches += [
            [[0.0] * self._match_feature_dim for _ in range(self.max_resources_per_uav)]
            for _ in range(missing_agents * self.max_tasks)
        ]
        return (
            [float(raw["time"]) / 1000.0]
            + [float(v) for row in tasks for v in row]
            + [float(v) for row in resources for v in row]
            + [float(v) for group in matches for row in group for v in row]
            + ([v for agent in self.agents for v in self.observe()[agent]["urgency_features"]]
               + [0.0] * (missing_agents * self.noop_index)
               if self.include_deadline_features else [])
        )

    def step(self, joint_actions: Mapping[str, int]):
        """一次接收所有 UAV 的动作，返回 (observations, team_reward, terminated, truncated, info)。

        分配不推进仿真时钟；若本轮没有成功分配，才推进到下一到达/完成事件。
        多 UAV 同时选择同一子任务时按固定 UAV id 顺序接受第一个，其余拒绝。
        """
        if self._base.state is None:
            raise RuntimeError("Call reset() before step()")
        if self._base.terminated or self._base.truncated:
            raise RuntimeError("Episode ended; reset before step()")
        if set(joint_actions) != set(self.agents):
            raise ValueError("joint_actions must contain exactly one action per UAV")

        obs = self.observe()  # 全体 UAV 使用同一份决策时刻的状态快照
        state = self._base.state
        rewards = self._base.rewards
        self._base.steps += 1
        reward_parts: Dict[str, float] = {}
        agent_events: Dict[str, Dict[str, Any]] = {}
        completed: List[AssignmentRecord] = []
        started: List[AssignmentRecord] = []
        claimed_tasks: set[str] = set()
        conflicts = 0
        total_invalid = 0
        for agent in self.agents:
            action = joint_actions[agent]
            local = obs[agent]
            status = "wait"
            pair = None
            if (not isinstance(action, Integral) or isinstance(action, bool)
                or not 0 <= action < self.action_dim
                or not local["action_mask"][action]):
                status = "invalid_action"
            elif action != self.noop_index:
                pair = local["action_labels"][action]
                assert pair is not None
                task_id, resource_id = pair
                if task_id in claimed_tasks:
                    status = "task_conflict"
                    conflicts += 1
                else:
                    # 原子二次检查：当前状态可能已经被其他 UAV 的分配改变。
                    task = state.get_subtask(task_id)
                    resource = state.get_resource(resource_id)
                    if self.executor.score_assignment(state, task_id, resource_id).feasible:
                        record = self.executor.assign(state, task_id, resource_id)
                        started.append(record)
                        claimed_tasks.add(task_id)
                        status = "assigned"
                    else:
                        status = "stale_action"
            if status in {"invalid_action", "task_conflict", "stale_action"}:
                total_invalid += 1
            agent_events[agent] = {"status": status, "assignment": pair}

        team_reward = 0.0
        if total_invalid:
            penalty = rewards.invalid_action * total_invalid
            reward_parts["invalid_actions"] = penalty
            team_reward += penalty
        if started:
            penalty = -rewards.energy_cost * sum(
                x.estimated_energy for x in started
            ) / self._base._energy_normalization()
            reward_parts["energy"] = penalty
            team_reward += penalty
            completed = self.executor.advance_time(state, state.now)
            elapsed = 0.0
            reason = "assigned"
        else:
            next_time = self.executor.next_event_time(state)
            if next_time is not None:
                elapsed = next_time - state.now
                completed = self.executor.advance_time(state, next_time)
                reason = "wait_for_event"
            else:
                elapsed = 0.0
                mask_has_any_assignment = any(
                    any(item["action_mask"][:-1]) for item in obs.values()
                )
                if mask_has_any_assignment:
                    reason = "idle_with_feasible_actions"
                    reward_parts["idle"] = rewards.invalid_action
                    team_reward += rewards.invalid_action
                else:
                    reason = "stalled"
                    self._base.terminated = True
                    self._base.status = "stalled"
                    reward_parts["stalled"] = rewards.stalled
                    team_reward += rewards.stalled
        if elapsed:
            penalty = -rewards.elapsed_time_cost * elapsed
            team_reward += penalty
            reward_parts["elapsed_time"] = penalty
        if completed:
            gain = 0.0
            for assignment in completed:
                task = state.get_subtask(assignment.subtask_id)
                bonus = (rewards.completion
                         + rewards.priority_bonus * self._base._normalize(task.priority, "max_priority")
                         + rewards.quality_bonus * assignment.estimated_quality)
                if task.deadline > 0 and assignment.actual_end_time is not None and assignment.actual_end_time <= task.deadline:
                    bonus += rewards.on_time_bonus
                gain += bonus
            reward_parts["completion"] = gain
            team_reward += gain
            # 超期仅在任务完成时扣一次，避免同一任务多次领取惩罚。
            late_loss = 0.0
            for assignment in completed:
                task = state.get_subtask(assignment.subtask_id)
                if task.deadline > 0 and assignment.actual_end_time is not None:
                    overdue = max(0.0, assignment.actual_end_time - task.deadline)
                    if overdue > 0.0:
                        late_loss += (rewards.late_fixed_penalty
                                      + rewards.late_time_penalty * overdue)
            if late_loss:
                reward_parts["lateness"] = -late_loss
                team_reward -= late_loss

        if self._base._all_finished():
            self._base.terminated = True
            self._base.status = "completed"
        elif not self._base.terminated and self._base.steps >= self._base.max_steps:
            self._base.truncated = True
            self._base.status = "step_limit"
        self._last_conflicts += conflicts
        info = self._info(self._base._info(elapsed_time=elapsed))
        info.update({
            "reason": reason,
            "agent_events": agent_events,
            "started": [(x.subtask_id, x.resource_id) for x in started],
            "completed": [x.subtask_id for x in completed],
            "reward_parts": reward_parts,
            "conflicts_this_step": conflicts,
        })
        return self.observe(), team_reward, self._base.terminated, self._base.truncated, info

    def add_subtask(self, task, predecessors=(), predecessor_data_sizes=None):
        state = self._base._require_running()
        if len(state.task_graph.subtasks) >= self.max_tasks:
            raise ValueError("New task exceeds max_tasks")
        self._base.add_subtask(task, predecessors, predecessor_data_sizes)

    def set_link_online(self, source_uav_id: str, target_uav_id: str, online: bool) -> None:
        self._base.set_link_online(source_uav_id, target_uav_id, online)

    def fail_resource(self, resource_id: str, *, retry_task: bool = True):
        return self._base.fail_resource(resource_id, retry_task=retry_task)

    def _info(self, source: Dict[str, Any]) -> Dict[str, Any]:
        return {**source, "agents": list(self.agents), "conflicts_total": self._last_conflicts}

    def _validate_capacities(self, raw):
        if len(raw["task_ids"]) > self.max_tasks:
            raise ValueError("Task count exceeds max_tasks")
        if len(raw["resource_ids"]) > self.max_agents * self.max_resources_per_uav:
            raise ValueError("Resource count exceeds fixed observation capacity")

    @staticmethod
    def _pad(rows: List[List[float]], count: int, dim: int) -> List[List[float]]:
        if len(rows) > count:
            raise ValueError("Exceeded configured padding capacity")
        return [list(map(float, row)) for row in rows] + [[0.0] * dim for _ in range(count - len(rows))]
