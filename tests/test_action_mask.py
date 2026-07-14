from pathlib import Path

from ubisched.graph.action_mask import ActionMaskBuilder
from ubisched.graph.match_matrix import MatchMatrixBuilder, RuleBasedScorer
from ubisched.graph.resource_graph import ResourceGraph
from ubisched.graph.task_graph import TaskGraph


ROOT = Path(__file__).resolve().parents[1]


def test_action_mask_flattens_feasible_matrix_and_adds_noop() -> None:
    task_graph = TaskGraph.from_yaml(ROOT / "configs/ubisched/task_graph_example.yaml")
    resource_graph = ResourceGraph.from_yaml(
        ROOT / "configs/ubisched/resource_graph_example.yaml"
    )
    scorer = RuleBasedScorer.from_yaml(ROOT / "configs/ubisched/match_scoring.yaml")
    matrix = MatchMatrixBuilder(scorer).build(task_graph, resource_graph)

    action_mask = ActionMaskBuilder().build(matrix)

    assert action_mask.action_mask == [1, 0, 0, 0, 1]
    assert action_mask.action_labels[0] == "assign(detect_target, uav_1_rgb_sensor)"
    assert action_mask.action_labels[-1] == "noop"
    assert action_mask.noop_index == 4
