"""第十阶段的可重复通信争用场景：两条图像依赖流和两个计算节点。"""
from __future__ import annotations

from ubisched.graph.task_graph import TaskGraph
from ubisched.graph.resource_graph import ResourceGraph
from ubisched.graph.match_matrix import RuleBasedScorer

def build_link_contention_case(second_link=False, bandwidth=5.0):
    task_graph = TaskGraph.from_dict({
        "task_graph_id": "link_contention",
        "subtasks": [
            {"subtask_id": "capture_a", "task_type": "sense", "priority": 5,
             "required_modalities_any": ["rgb"], "min_quality": 0.5},
            {"subtask_id": "capture_b", "task_type": "sense", "priority": 5,
             "required_modalities_any": ["rgb"], "min_quality": 0.5},
            {"subtask_id": "infer_a", "task_type": "classify", "compute_cycles": 10},
            {"subtask_id": "infer_b", "task_type": "classify", "compute_cycles": 10},
        ],
        "edges": [
            {"src_subtask_id": "capture_a", "dst_subtask_id": "infer_a", "data_size_mb": 10},
            {"src_subtask_id": "capture_b", "dst_subtask_id": "infer_b", "data_size_mb": 10},
        ],
    })
    graph = ResourceGraph.from_dict({
        "resource_graph_id": "link_contention",
        "resources": [
            {"resource_id": "camera", "owner_uav_id": "uav1", "resource_type": "sensor",
             "modalities": ["rgb"], "sensing_quality": {"rgb": 0.9},
             "power": 1, "remaining_energy": 100, "link_rate": 10},
            {"resource_id": "cpu_a", "owner_uav_id": "uav2", "resource_type": "compute",
             "cpu_frequency": 10, "power": 1, "remaining_energy": 100},
            {"resource_id": "cpu_b", "owner_uav_id": "uav3" if second_link else "uav2",
             "resource_type": "compute", "cpu_frequency": 10,
             "power": 1, "remaining_energy": 100},
        ],
        "communication_links": [
            {"source_uav_id": "uav1", "target_uav_id": "uav2",
             "bandwidth_mb_s": bandwidth, "energy_per_mb": 0.2},
            {"source_uav_id": "uav1", "target_uav_id": "uav3",
             "bandwidth_mb_s": bandwidth, "energy_per_mb": 0.2},
        ],
    })
    scorer = RuleBasedScorer({
        "strict_deadlines": False,
        "normalization": {"max_latency": 100, "max_energy": 1000,
                          "max_cpu_frequency": 10, "max_priority": 10},
        "defaults": {"task_type_base_time": {"sense": 1, "classify": 0}},
    })
    return task_graph, graph, scorer


