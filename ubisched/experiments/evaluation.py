from __future__ import annotations

"""统一评估规则、随机、MAPPO：同环境，同场景，同奖励。"""

from dataclasses import asdict, dataclass
import math
import random
from typing import Callable, Mapping

from ubisched.scheduling.multi_agent_env import MultiAgentSchedulerEnv

POLICIES = ("random_feasible", "greedy_score", "earliest_deadline")


@dataclass
class EvalMetrics:
    policy: str
    scenario: str
    scenario_seed: int
    train_seed: int | None
    reward: float
    completion_rate: float
    deadline_met_rate: float
    finished_tasks: int
    total_tasks: int
    makespan: float
    total_energy: float
    energy_per_finished: float | None
    quality_mean_finished: float | None
    conflicts: int
    decisions: int
    status: str
    avoidable_wait_steps: int = 0
    attempted_conflicts: int = 0
    late_finished_tasks: int = 0
    total_lateness: float = 0.0

    def to_dict(self):
        return asdict(self)


def choose_rule_actions(env: MultiAgentSchedulerEnv, observations: Mapping, *,
                        policy: str, rng: random.Random | None = None) -> dict[str, int]:
    """基线可见全局任务表；评分与执行使用同一实时通信预约估算。

    一次决策中每个 UAV 最多领一个任务，任务最多由一个 UAV 领取。
    规则策略从同一快照选择，不在策略内部修改环境。
    """
    if policy not in POLICIES:
        raise ValueError(f"Unknown rule policy: {policy}")
    rng = rng or random.Random(0)
    candidates = []
    for agent in env.agents:
        local = observations[agent]
        for action, valid in enumerate(local["action_mask"][:-1]):
            if not valid:
                continue
            pair = local["action_labels"][action]
            if pair is None:
                continue
            task_id, resource_id = pair
            task = env.state.get_subtask(task_id)
            entry = env.executor.score_assignment(env.state, task_id, resource_id)
            candidates.append((agent, action, task_id, float(entry.match_score), float(task.deadline),
                               float(task.priority)))
    if policy == "random_feasible":
        rng.shuffle(candidates)
    elif policy == "greedy_score":
        candidates.sort(key=lambda row: (-row[3], -row[5], row[4], row[2], row[0]))
    else:
        candidates.sort(key=lambda row: (row[4] if row[4] > 0 else math.inf,
                                         -row[5], -row[3], row[2], row[0]))
    joint = {agent: env.noop_index for agent in env.agents}
    assigned_tasks = set()
    for agent, action, task_id, *_ in candidates:
        if joint[agent] == env.noop_index and task_id not in assigned_tasks:
            joint[agent] = action
            assigned_tasks.add(task_id)
    return joint


def run_episode(env: MultiAgentSchedulerEnv, action_fn: Callable,
                *, policy: str, scenario: str, scenario_seed: int,
                train_seed: int | None = None) -> EvalMetrics:
    """action_fn(env, observations)-> {uav:action}，固定返回指标。"""
    obs, _ = env.reset()
    reward_total = 0.0
    info = None
    avoidable_wait_steps = 0
    attempted_conflicts = 0
    while True:
        actions = action_fn(env, obs)
        feasible_now = any(any(x["action_mask"][:-1]) for x in obs.values())
        obs, reward, terminated, truncated, info = env.step(actions)
        if feasible_now and not info["started"]:
            avoidable_wait_steps += 1
        attempted_conflicts += info["conflicts_this_step"]
        reward_total += reward
        if terminated or truncated:
            break
    assert info is not None and env.state is not None
    finished = sum(t.state == "finished" for t in env.state.task_graph.subtasks)
    return EvalMetrics(
        policy=policy, scenario=scenario, scenario_seed=scenario_seed,
        train_seed=train_seed, reward=reward_total,
        completion_rate=info["completion_rate"],
        deadline_met_rate=info["deadline_met_rate"],
        finished_tasks=finished, total_tasks=info["total_tasks"],
        makespan=info["time"], total_energy=info["total_energy"],
        energy_per_finished=(info["total_energy"] / finished if finished else None),
        quality_mean_finished=(sum(a.estimated_quality for a in env.state.assignments
                                   if a.status == "finished") / finished if finished else None),
        conflicts=info["conflicts_total"], decisions=info["steps"], status=info["status"],
        avoidable_wait_steps=avoidable_wait_steps,
        attempted_conflicts=attempted_conflicts,
        late_finished_tasks=sum(
            1 for a in env.state.assignments if a.status == "finished"
            and env.state.get_subtask(a.subtask_id).deadline > 0
            and a.actual_end_time is not None
            and a.actual_end_time > env.state.get_subtask(a.subtask_id).deadline
        ),
        total_lateness=sum(
            max(0.0, a.actual_end_time - env.state.get_subtask(a.subtask_id).deadline)
            for a in env.state.assignments if a.status == "finished"
            and a.actual_end_time is not None
            and env.state.get_subtask(a.subtask_id).deadline > 0
        ),
    )


def run_rule_episode(*, scenario_seed: int, scenario: str, policy: str) -> EvalMetrics:
    from ubisched.experiments.scenarios import make_env
    rng = random.Random(scenario_seed + 3917)
    return run_episode(make_env(scenario_seed, scenario=scenario),
                       lambda e, obs: choose_rule_actions(e, obs, policy=policy, rng=rng),
                       policy=policy, scenario=scenario, scenario_seed=scenario_seed)


def run_mappo_episode(algo, *, scenario_seed: int, scenario: str, train_seed: int,
                      policy_name: str = "mappo_mlp"):
    """冻结模型、用与训练相同的条件采样规则作确定性测试。"""
    from ubisched.experiments.scenarios import make_env
    env = make_env(
        scenario_seed, scenario=scenario,
        deadline_features=getattr(algo, "deadline_features", False),
    )
    was_training = algo.actor.training
    algo.actor.eval()
    try:
        def action_fn(e, obs):
            _, _, actions, _ = algo.select_actions(e, obs, greedy=True)
            return dict(zip(e.agents, actions.tolist()))
        return run_episode(env, action_fn, policy=policy_name, scenario=scenario,
                           scenario_seed=scenario_seed, train_seed=train_seed)
    finally:
        algo.actor.train(was_training)
