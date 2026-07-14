from pathlib import Path

from ubisched.graph.match_matrix import MatchMatrixBuilder, RuleBasedScorer
from ubisched.graph.resource_graph import ResourceGraph
from ubisched.graph.task_graph import TaskGraph


ROOT = Path(__file__).resolve().parents[1]


def _build_matrix():
    task_graph = TaskGraph.from_yaml(ROOT / "configs/ubisched/task_graph_example.yaml")
    resource_graph = ResourceGraph.from_yaml(
        ROOT / "configs/ubisched/resource_graph_example.yaml"
    )
    scorer = RuleBasedScorer.from_yaml(ROOT / "configs/ubisched/match_scoring.yaml")
    return MatchMatrixBuilder(scorer).build(task_graph, resource_graph)


def test_match_matrix_outputs_required_fields() -> None:
    matrix = _build_matrix()
    entry = matrix.entries[0][0]

    assert isinstance(entry.feasible, bool)
    assert 0.0 <= entry.quality_score <= 1.0
    assert 0.0 <= entry.latency_cost <= 1.0
    assert 0.0 <= entry.energy_cost <= 1.0
    assert 0.0 <= entry.distance_cost <= 1.0
    assert 0.0 <= entry.load_cost <= 1.0
    assert 0.0 <= entry.match_score <= 1.0


def test_required_modalities_any_allows_one_supported_modality() -> None:
    matrix = _build_matrix()

    assert matrix.feasible[0][0] == 1
    assert matrix.entries[0][0].quality_score == 0.85


def test_pending_subtask_is_not_feasible() -> None:
    matrix = _build_matrix()

    assert matrix.feasible[1] == [0, 0]


def test_compute_resource_cannot_run_sensing_task() -> None:
    matrix = _build_matrix()

    assert matrix.feasible[0][1] == 0
