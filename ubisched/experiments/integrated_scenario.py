from __future__ import annotations

"""第十一阶段：任务图、异构感算资源、共享通信链路的统一实验场景。

所有数值均为仿真参数，不代表 AirSim/实机实测。
同一 seed 下任务完全相同。fast/slow/outage 只调整链路，
contended 额外禁用本地和备用 CPU，专用于检测共享链路排队。
"""

import random

from ubisched.graph.task_graph import TaskGraph
from ubisched.graph.resource_graph import ResourceGraph
from ubisched.graph.match_matrix import RuleBasedScorer
from ubisched.scheduling.multi_agent_env import MultiAgentSchedulerEnv
from ubisched.scheduling.scheduler_env import RewardConfig
from ubisched.config import make_scorer, make_env

NETWORK_CONDITIONS = ("fast", "slow", "outage", "contended")
# contended 是受限资源压力测试，其余三种场景仅改变 UAV1->UAV2 链路。


def build_integrated_case(seed: int, *, condition: str = "fast", pairs: int = 3):
    if condition not in NETWORK_CONDITIONS:
        raise ValueError(f"Invalid network condition {condition!r}")
    if not 1 <= pairs <= 3:
        raise ValueError("pairs must be between 1 and 3, within max_tasks=8")
    rng = random.Random(seed)
    # 2 架遥感相机共享 UAV1，UAV2 有两个异构 CPU；UAV3 可作为替代节点。
    resources = [
        {"resource_id": f"cam_{i}", "owner_uav_id": "UAV1", "resource_type": "sensor",
         "modalities": ["rgb"], "sensing_quality": {"rgb": 0.87 + i * 0.025},
         "power": 1, "remaining_energy": 300, "link_rate": 100}
        for i in range(2)
    ]
    resources.extend([
        {"resource_id": "cpu_local", "owner_uav_id": "UAV1", "resource_type": "compute",
         "cpu_frequency": 2.2, "power": 1.3, "remaining_energy": 400, "online": condition != "contended"},
        {"resource_id": "cpu_fast_a", "owner_uav_id": "UAV2", "resource_type": "compute",
         "cpu_frequency": 10.0, "power": 1.2, "remaining_energy": 400},
        {"resource_id": "cpu_fast_b", "owner_uav_id": "UAV2", "resource_type": "compute",
         "cpu_frequency": 8.0, "power": 1.1, "remaining_energy": 400},
        {"resource_id": "cpu_backup", "owner_uav_id": "UAV3", "resource_type": "compute",
         "cpu_frequency": 4.0, "power": 1.2, "remaining_energy": 400,
         "online": condition != "contended"},
    ])
    bandwidth = {"fast": 20.0, "slow": 1.0, "outage": 20.0, "contended": 4.0}[condition]
    graph = ResourceGraph.from_dict({
        "resource_graph_id": f"resources_{seed}_{condition}",
        "resources": resources,
        "communication_links": [
            {"source_uav_id": "UAV1", "target_uav_id": "UAV2",
             "bandwidth_mb_s": bandwidth, "latency_s": 0.1,
             "energy_per_mb": 0.015, "online": condition != "outage"},
            {"source_uav_id": "UAV1", "target_uav_id": "UAV3",
             "bandwidth_mb_s": 2.5, "latency_s": 0.1,
             "energy_per_mb": 0.02, "online": True},
        ],
    })
    tasks, edges = [], []
    for i in range(pairs):
        priority = rng.randint(4, 10)
        # 让不同 seed 具备不同采集量、计算量和紧迫程度。
        data_mb = round(rng.uniform(8, 12), 3)
        cycles = round(rng.uniform(8, 12), 3)
        capture_id, infer_id = f"capture_{i}", f"infer_{i}"
        tasks.extend([
            {"subtask_id": capture_id, "task_type": "sense", "priority": priority,
             "required_modalities_any": ["rgb"], "min_quality": 0.8,
             "deadline": 4.0 + i * 1.0, "max_latency": 15,
             "arrival_time": 0.0 if i < 2 else 1.0},
            {"subtask_id": infer_id, "task_type": "classify", "priority": priority,
             "compute_cycles": cycles, "deadline": rng.uniform(4.5, 8.0) + i * 1.0,
             "max_latency": 30, "arrival_time": 0.0},
        ])
        edges.append({"src_subtask_id": capture_id, "dst_subtask_id": infer_id,
                      "data_size_mb": data_mb})
    rng.shuffle(tasks)  # 避免策略记忆固定输入位置。
    task_graph = TaskGraph.from_dict({"task_graph_id": f"mixed_{seed}",
                                     "subtasks": tasks, "edges": edges})
    scorer = make_scorer()
    return task_graph, graph, scorer


def make_integrated_env(seed: int, *, condition: str = "fast", pairs: int = 3,
                        max_steps: int = 90, critical_path: bool = False) -> MultiAgentSchedulerEnv:
    tasks, resources, scorer = build_integrated_case(seed, condition=condition, pairs=pairs)
    return make_env(tasks, resources, max_steps=max_steps, critical_path=critical_path)
