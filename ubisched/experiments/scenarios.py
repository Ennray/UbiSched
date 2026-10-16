from __future__ import annotations

"""阶段4的确定性、可复现任务场景生成器。

只变化场景本身，不修改评分器。不同策略必须使用相同 seed 的场景。
阶段4暂固定 UAV 的身份与每 UAV 资源槽数，以匹配阶段3的定长 MLP Actor。
"""

from copy import deepcopy
from pathlib import Path
import random

from ubisched.graph.match_matrix import RuleBasedScorer
from ubisched.graph.resource_graph import ResourceGraph
from ubisched.graph.task_graph import SubTask, TaskEdge, TaskGraph
from ubisched.scheduling.multi_agent_env import MultiAgentSchedulerEnv
from ubisched.scheduling.scheduler_env import RewardConfig

ROOT = Path(__file__).resolve().parents[2]
SUPPORTED_SCENARIOS = ("normal", "urgent", "staggered")
STAGE7_SCENARIOS = SUPPORTED_SCENARIOS + ("dependency",)


def build_scenario(seed: int, *, scenario: str = "normal", pairs: int | None = None,
                   num_uavs: int = 3):
    """返回可复现的图和评分器；不依赖进程全局随机种子。"""
    if scenario not in STAGE7_SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario!r}")
    if num_uavs not in (2, 3):
        raise ValueError("Supported UAV counts for this scenario generator: 2 or 3")
    rng = random.Random(seed)
    if pairs is None:
        pairs = rng.randint(2, 4)
    if not 1 <= pairs <= 4:
        raise ValueError("pairs must be between 1 and 4 (max_tasks=8)")

    resources = ResourceGraph.from_yaml(ROOT / "configs/ubisched/resource_graph_example.yaml")
    left = resources.resources[0]
    cpu = resources.resources[1]
    right = deepcopy(left)
    right.owner_uav_id = "uav_3"
    right.resource_id = "uav_3_rgb_sensor"
    left.location = [90.0, 46.0, 18.0]
    right.location = [110.0, 57.0, 18.0]
    left.sensing_quality = {"rgb": rng.uniform(0.84, 0.96), "infrared": rng.uniform(0.78, 0.90)}
    right.sensing_quality = {"rgb": rng.uniform(0.75, 0.89), "infrared": rng.uniform(0.75, 0.88)}
    left.power = rng.uniform(27.0, 38.0)
    right.power = rng.uniform(18.0, 27.0)
    left.link_rate = rng.uniform(9.0, 14.0)
    right.link_rate = rng.uniform(8.0, 13.0)
    left.cpu_frequency = rng.uniform(1.0e9, 1.8e9)
    right.cpu_frequency = rng.uniform(1.0e9, 1.8e9)
    left.remaining_energy = right.remaining_energy = 10000.0
    cpu.cpu_frequency = rng.uniform(5.5e9, 9.0e9)
    cpu.link_rate = rng.uniform(17.0, 28.0)
    cpu.power = rng.uniform(45.0, 65.0)
    cpu.queue_length = rng.uniform(0, 3)
    cpu.remaining_energy = 15000.0
    resources.resources = [left, cpu, right] if num_uavs == 3 else [left, cpu]

    tasks: list[SubTask] = []
    edges: list[TaskEdge] = []
    for i in range(pairs):
        arrival = 0.0 if scenario != "staggered" else float(i * 0.8)
        target_location = [rng.uniform(93.0, 110.0), rng.uniform(47.0, 60.0), 0.0]
        priority = rng.randint(4, 10)
        min_quality = rng.uniform(0.69, 0.82)
        if scenario in {"urgent", "dependency"}:
            # 竞争激烈、但整体并非天然无解：用截止时间区分短视贪心和 EDF。
            sensing_deadline = arrival + rng.uniform(6.0, 9.0) + i * 1.1
            classify_deadline = arrival + rng.uniform(12.0, 17.0) + i * 1.5
        elif scenario == "staggered":
            # 任务逐批到达，仍有有限执行时窗。
            sensing_deadline = arrival + rng.uniform(6.0, 9.0) + i * 0.4
            classify_deadline = arrival + rng.uniform(12.0, 17.0) + i * 0.8
        else:
            sensing_deadline = arrival + rng.uniform(10.0, 17.0) + i * 1.5
            classify_deadline = arrival + rng.uniform(17.0, 27.0) + i * 1.5
        detect_id, classify_id = f"detect_{i}", f"classify_{i}"
        tasks.append(SubTask(
            subtask_id=detect_id, task_type="detect", priority=priority,
            deadline=sensing_deadline, location=target_location,
            required_modalities_any=["rgb", "infrared"], min_quality=min_quality,
            data_size=rng.uniform(8.0, 22.0), compute_cycles=rng.uniform(0.6e9, 1.5e9),
            max_latency=25.0, resource_count_min=1, resource_count_max=1,
            state="pending", arrival_time=arrival,
        ))
        tasks.append(SubTask(
            subtask_id=classify_id, task_type="classify", priority=max(1, priority - rng.randint(0, 2)),
            deadline=classify_deadline, location=target_location,
            required_modalities_any=[], min_quality=0.0,
            data_size=rng.uniform(18.0, 37.0), compute_cycles=rng.uniform(5.0e9, 12.0e9),
            max_latency=35.0, resource_count_min=1, resource_count_max=1,
            state="pending", arrival_time=arrival,
        ))
        edges.append(TaskEdge(detect_id, classify_id))
    if scenario == "dependency" and pairs >= 2:
        # 分叉与汇合：检测0解锁分类0/分类1，分类1还依赖检测1。
        # 分类2再依赖检测1与检测2（如果有）。
        for i in range(1, pairs):
            edges.append(TaskEdge(f"detect_{i-1}", f"classify_{i}"))
    # 顺序并非任务优先级；打散索引避免模型只记住固定槽位。
    rng.shuffle(tasks)
    return (TaskGraph(f"{scenario}_{seed}", tasks, edges), resources,
            RuleBasedScorer.from_yaml(ROOT / "configs/ubisched/match_scoring.yaml"))


def make_env(seed: int, *, scenario: str = "normal", pairs: int | None = None,
             max_steps: int = 70, deadline_features: bool = False,
             num_uavs: int = 3, dependency_features: bool = False,
             critical_path_features: bool = False, soft_deadlines: bool = False,
             reward_config: RewardConfig | None = None) -> MultiAgentSchedulerEnv:
    tasks, resources, scorer = build_scenario(
        seed, scenario=scenario, pairs=pairs, num_uavs=num_uavs
    )
    if soft_deadlines:
        scorer.strict_deadlines = False
    return MultiAgentSchedulerEnv(
        tasks, resources, scorer, max_tasks=8,
        max_resources_per_uav=1, max_agents=3, max_steps=max_steps,
        include_deadline_features=deadline_features,
        include_dependency_features=dependency_features,
        include_critical_path_features=critical_path_features,
        reward_config=reward_config,
    )
