"""第九阶段：可重复的双 UAV 感知与计算协同示例场景。

仅供算法接口和物理约束校验，不代表真实测得的 AirSim 性能。
"""
from __future__ import annotations

from ubisched.graph.task_graph import TaskGraph
from ubisched.graph.resource_graph import ResourceGraph
from ubisched.graph.match_matrix import RuleBasedScorer


def build_sensing_compute_case(link_bandwidth: float = 5.0, link_online: bool = True):
    """UAV1采集数据，计算任务可由UAV1或UAV2执行。

    10MB图像，UAV1本机计算5秒；UAV2计算1秒加链路传输。
    若传输后计算超过10秒，远端计算被硬实时约束屏蔽。
    """
    task_graph = TaskGraph.from_dict({
        "task_graph_id": "stage9_demo",
        "subtasks": [
            {"subtask_id": "capture", "task_type": "sense", "priority": 10,
             "required_modalities_any": ["rgb"], "min_quality": 0.5,
             "deadline": 60, "max_latency": 20},
            {"subtask_id": "infer", "task_type": "classify", "priority": 10,
             "compute_cycles": 10, "deadline": 60, "max_latency": 10},
        ],
        "edges": [{"src_subtask_id": "capture", "dst_subtask_id": "infer",
                   "data_size_mb": 10}],
    })
    resource_graph = ResourceGraph.from_dict({
        "resource_graph_id": "stage9_resources",
        "resources": [
            {"resource_id": "camera", "owner_uav_id": "UAV1",
             "resource_type": "sensor", "modalities": ["rgb"],
             "sensing_quality": {"rgb": 0.9}, "remaining_energy": 200,
             "power": 1, "link_rate": 10},
            {"resource_id": "cpu_local", "owner_uav_id": "UAV1",
             "resource_type": "compute", "cpu_frequency": 2,
             "remaining_energy": 100, "power": 1},
            {"resource_id": "cpu_remote", "owner_uav_id": "UAV2",
             "resource_type": "compute", "cpu_frequency": 10,
             "remaining_energy": 100, "power": 1},
        ],
        "communication_links": [
            {"source_uav_id": "UAV1", "target_uav_id": "UAV2",
             "bandwidth_mb_s": link_bandwidth,
             "latency_s": 0.2, "energy_per_mb": 0.2,
             "online": link_online},
        ],
    })
    scorer = RuleBasedScorer({
        "normalization": {"max_latency": 100, "max_energy": 1000,
                          "max_distance": 100, "max_priority": 10,
                          "max_cpu_frequency": 10, "max_queue_length": 10},
        "defaults": {"task_type_base_time": {"sense": 1, "classify": 0}},
        "match_weights": {"quality": 0.5, "latency": 0.5},
    })
    return task_graph, resource_graph, scorer
