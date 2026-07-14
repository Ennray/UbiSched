from pathlib import Path

import pytest

from ubisched.graph.resource_graph import ResourceGraph, ResourceNode


ROOT = Path(__file__).resolve().parents[1]


def test_load_resource_graph_example() -> None:
    graph = ResourceGraph.from_yaml(ROOT / "configs/ubisched/resource_graph_example.yaml")

    assert graph.resource_graph_id == "resources_t0"
    assert graph.resource_ids() == ["uav_1_rgb_sensor", "uav_2_compute"]
    assert graph.resources[0].resource_type == "sensor"
    assert graph.resources[1].resource_type == "compute"


def test_uav_is_not_executable_resource_type() -> None:
    with pytest.raises(ValueError):
        ResourceNode.from_dict(
            {
                "resource_id": "uav_1",
                "resource_type": "uav",
                "owner_uav_id": "uav_1",
            }
        )
