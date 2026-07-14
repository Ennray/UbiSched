from pathlib import Path

import pytest

from ubisched.graph.match_matrix import RuleBasedScorer
from ubisched.graph.resource_graph import ResourceGraph
from ubisched.graph.task_graph import TaskGraph
from ubisched.scheduling.assignment_executor import AssignmentExecutor
from ubisched.scheduling.rule_based_scheduler import RuleBasedScheduler
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
    return state, RuleBasedScheduler(AssignmentExecutor(scorer))


def test_selects_only_feasible_highest_score_assignment() -> None:
    state, scheduler = _build_scheduler()
    matrix = scheduler.executor.build_match_matrix(state)

    selected = scheduler.select_assignment(matrix)

    assert selected is not None
    assert selected.subtask_id == "detect_target"
    assert selected.resource_id == "uav_1_rgb_sensor"
    assert selected.match_score == pytest.approx(matrix.match_score[0][0])


def test_runs_complete_task_graph_without_hardcoded_actions() -> None:
    state, scheduler = _build_scheduler()

    result = scheduler.run(state)

    assert result.status == "completed"
    assert [
        (record.subtask_id, record.resource_id)
        for record in result.assignments
    ] == [
        ("detect_target", "uav_1_rgb_sensor"),
        ("classify_target", "uav_2_compute"),
    ]
    assert [task.state for task in state.task_graph.subtasks] == [
        "finished",
        "finished",
    ]


def test_reports_makespan_energy_and_deadline_rate() -> None:
    state, scheduler = _build_scheduler()

    result = scheduler.run(state)

    assert result.makespan == pytest.approx(9.25)
    assert result.total_energy == pytest.approx(412.0)
    assert result.deadline_met_rate == pytest.approx(1.0)
    assert result.unfinished_subtask_ids == []


def test_reports_stalled_when_no_resource_is_feasible() -> None:
    state, scheduler = _build_scheduler()
    for resource in state.resource_graph.resources:
        resource.remaining_energy = 0.0

    result = scheduler.run(state)

    assert result.status == "stalled"
    assert result.assignments == []
    assert result.unfinished_subtask_ids == [
        "detect_target",
        "classify_target",
    ]


def test_rejects_non_positive_iteration_limit() -> None:
    state, scheduler = _build_scheduler()

    with pytest.raises(ValueError, match="positive"):
        scheduler.run(state, max_iterations=0)
