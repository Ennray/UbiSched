"""Small fixed scenario for MAPPO component regression tests."""
from copy import deepcopy
from pathlib import Path

from ubisched.graph.match_matrix import RuleBasedScorer
from ubisched.graph.resource_graph import ResourceGraph
from ubisched.graph.task_graph import TaskGraph, TaskEdge
from ubisched.scheduling.multi_agent_env import MultiAgentSchedulerEnv

ROOT = Path(__file__).resolve().parents[2]

def make_env() -> MultiAgentSchedulerEnv:
    tasks = TaskGraph.from_yaml(ROOT / "configs/ubisched/task_graph_example.yaml")
    resources = ResourceGraph.from_yaml(ROOT / "configs/ubisched/resource_graph_example.yaml")
    backup = deepcopy(resources.resources[0])
    backup.resource_id = "uav_3_rgb_sensor"
    backup.owner_uav_id = "uav_3"
    backup.power = 24.0
    backup.sensing_quality = {"rgb": 0.79, "infrared": 0.76}
    resources.resources.append(backup)
    # 新增独立检测任务及其后续计算任务，使两个传感器可以真正并行。
    detect2 = deepcopy(tasks.subtasks[0])
    detect2.subtask_id = "detect_target_2"
    detect2.location = [102.0, 51.0, 0.0]
    classify2 = deepcopy(tasks.subtasks[1])
    classify2.subtask_id = "classify_target_2"
    tasks.subtasks.extend([detect2, classify2])
    tasks.edges.append(TaskEdge("detect_target_2", "classify_target_2"))
    return MultiAgentSchedulerEnv(
        tasks, resources,
        RuleBasedScorer.from_yaml(ROOT / "configs/ubisched/match_scoring.yaml"),
        max_tasks=4, max_resources_per_uav=1, max_agents=3,
        max_steps=60,
    )
