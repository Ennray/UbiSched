"""Prevent unsupported modality from being assigned even with min_quality=0."""
from ubisched.graph.task_graph import TaskGraph
from ubisched.graph.resource_graph import ResourceGraph
from ubisched.graph.match_matrix import MatchMatrixBuilder, RuleBasedScorer


def test_zero_quality_requirement_does_not_allow_wrong_sensor_type():
    task = TaskGraph.from_dict({"task_graph_id": "g", "subtasks": [
        {"subtask_id": "t", "task_type": "sense", "required_modalities_any": ["infrared"],
         "min_quality": 0, "state": "pending"}]})
    resources = ResourceGraph.from_dict({"resource_graph_id": "r", "resources": [
        {"resource_id": "rgb", "owner_uav_id": "UAV1", "resource_type": "sensor",
         "modalities": ["rgb"], "sensing_quality": {"rgb": 0.9}},
        {"resource_id": "ir", "owner_uav_id": "UAV1", "resource_type": "sensor",
         "modalities": ["infrared"], "sensing_quality": {"infrared": 0.9}},
    ]})
    matrix = MatchMatrixBuilder(RuleBasedScorer()).build(task, resources)
    assert matrix.feasible == [[0, 1]]
