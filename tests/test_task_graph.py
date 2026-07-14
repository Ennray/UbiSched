from pathlib import Path

from ubisched.graph.task_graph import TaskGraph, build_precedence_matrix


ROOT = Path(__file__).resolve().parents[1]


def test_load_task_graph_example() -> None:
    graph = TaskGraph.from_yaml(ROOT / "configs/ubisched/task_graph_example.yaml")

    assert graph.task_graph_id == "mission_001"
    assert graph.subtask_ids() == ["detect_target", "classify_target"]
    assert len(graph.edges) == 1
    assert graph.subtasks[0].required_modalities_any == ["rgb", "infrared"]


def test_precedence_updates_pending_to_ready() -> None:
    graph = TaskGraph.from_yaml(ROOT / "configs/ubisched/task_graph_example.yaml")

    graph.update_ready_states()
    assert graph.get_subtask("classify_target").state == "pending"

    graph.get_subtask("detect_target").state = "finished"
    graph.update_ready_states()

    assert graph.get_subtask("classify_target").state == "ready"


def test_build_precedence_matrix() -> None:
    graph = TaskGraph.from_yaml(ROOT / "configs/ubisched/task_graph_example.yaml")

    assert build_precedence_matrix(graph) == [[0, 1], [0, 0]]
