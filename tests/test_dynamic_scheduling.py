from pathlib import Path

import pytest

from ubisched.graph.match_matrix import RuleBasedScorer
from ubisched.graph.resource_graph import ResourceGraph
from ubisched.graph.task_graph import TaskGraph
from ubisched.scheduling.assignment_executor import AssignmentExecutor
from ubisched.scheduling.scheduling_state import SchedulingState


ROOT = Path(__file__).resolve().parents[1]


def _build_scheduler():
    task_graph = TaskGraph.from_yaml(
        ROOT / "configs/ubisched/task_graph_example.yaml"
    )
    resource_graph = ResourceGraph.from_yaml(
        ROOT / "configs/ubisched/resource_graph_example.yaml"
    )
    scorer = RuleBasedScorer.from_yaml(
        ROOT / "configs/ubisched/match_scoring.yaml"
    )
    state = SchedulingState(task_graph, resource_graph)
    return state, AssignmentExecutor(scorer)


def test_assign_updates_task_resource_energy_and_record() -> None:
    state, executor = _build_scheduler()
    resource = state.get_resource("uav_1_rgb_sensor")
    initial_energy = resource.remaining_energy

    record = executor.assign(
        state,
        "detect_target",
        "uav_1_rgb_sensor",
    )

    assert state.get_subtask("detect_target").state == "running"
    assert resource.occupied is True
    assert resource.release_time == record.completion_time
    assert resource.remaining_energy == pytest.approx(
        initial_energy - record.estimated_energy
    )
    assert record.start_time == 0.0
    assert record.estimated_latency == pytest.approx(5.0)
    assert record.estimated_energy == pytest.approx(152.0)


def test_infeasible_assignment_is_rejected_without_state_change() -> None:
    state, executor = _build_scheduler()

    with pytest.raises(ValueError, match="Infeasible assignment"):
        executor.assign(
            state,
            "detect_target",
            "uav_2_compute",
        )

    assert state.get_subtask("detect_target").state == "ready"
    assert state.get_resource("uav_2_compute").occupied is False
    assert state.assignments == []


def test_advance_before_completion_keeps_assignment_running() -> None:
    state, executor = _build_scheduler()
    record = executor.assign(
        state,
        "detect_target",
        "uav_1_rgb_sensor",
    )

    completed = executor.advance_time(state, record.completion_time - 0.1)

    assert completed == []
    assert record.status == "running"
    assert state.get_subtask("detect_target").state == "running"
    assert state.get_resource("uav_1_rgb_sensor").occupied is True


def test_completion_releases_resource_and_unlocks_successor() -> None:
    state, executor = _build_scheduler()
    record = executor.assign(
        state,
        "detect_target",
        "uav_1_rgb_sensor",
    )

    completed = executor.advance_to_next_event(state)

    assert completed == [record]
    assert record.status == "finished"
    assert state.get_subtask("detect_target").state == "finished"
    assert state.get_resource("uav_1_rgb_sensor").occupied is False
    assert state.get_subtask("classify_target").state == "ready"


def test_rebuilt_matrix_allows_successor_on_compute_resource() -> None:
    state, executor = _build_scheduler()
    executor.assign(
        state,
        "detect_target",
        "uav_1_rgb_sensor",
    )
    executor.advance_to_next_event(state)

    matrix = executor.build_match_matrix(state)
    classify_index = matrix.subtask_ids.index("classify_target")
    compute_index = matrix.resource_ids.index("uav_2_compute")

    assert matrix.feasible[classify_index][compute_index] == 1


def test_complete_two_stage_task_graph() -> None:
    state, executor = _build_scheduler()
    executor.assign(state, "detect_target", "uav_1_rgb_sensor")
    executor.advance_to_next_event(state)
    executor.assign(state, "classify_target", "uav_2_compute")
    executor.advance_to_next_event(state)

    assert [task.state for task in state.task_graph.subtasks] == [
        "finished",
        "finished",
    ]
    assert all(not resource.occupied for resource in state.resource_graph.resources)
    assert executor.build_action_mask(state).action_mask == [0, 0, 0, 0, 1]


def test_time_cannot_move_backwards() -> None:
    state, executor = _build_scheduler()
    executor.advance_time(state, 1.0)

    with pytest.raises(ValueError, match="earlier"):
        executor.advance_time(state, 0.5)
