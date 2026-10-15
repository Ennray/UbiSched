"""第一阶段新增的动态任务到达、资源故障和恢复行为回归测试。"""

from copy import deepcopy
from pathlib import Path

import pytest

from ubisched.graph.match_matrix import RuleBasedScorer
from ubisched.graph.resource_graph import ResourceGraph
from ubisched.graph.task_graph import SubTask, TaskGraph
from ubisched.scheduling.assignment_executor import AssignmentExecutor
from ubisched.scheduling.rule_based_scheduler import RuleBasedScheduler
from ubisched.scheduling.scheduling_state import SchedulingState

ROOT = Path(__file__).resolve().parents[1]


def make_env():
    task_graph = TaskGraph.from_yaml(ROOT / "configs/ubisched/task_graph_example.yaml")
    resource_graph = ResourceGraph.from_yaml(
        ROOT / "configs/ubisched/resource_graph_example.yaml"
    )
    scorer = RuleBasedScorer.from_yaml(ROOT / "configs/ubisched/match_scoring.yaml")
    state = SchedulingState(task_graph, resource_graph)
    executor = AssignmentExecutor(scorer)
    return state, executor


def test_future_arrival_is_not_available_early_and_scheduler_waits():
    state, executor = make_env()
    state.get_subtask("detect_target").arrival_time = 8.0
    state.task_graph.update_ready_states(state.now)

    assert executor.build_match_matrix(state).feasible[0] == [0, 0]
    assert executor.next_event_time(state) == 8.0

    result = RuleBasedScheduler(executor).run(state)
    assert result.status == "completed"
    assert result.assignments[0].start_time == pytest.approx(8.0)
    assert result.end_time == pytest.approx(17.25)


def test_configured_ready_task_is_blocked_until_arrival():
    state, executor = make_env()
    task = state.get_subtask("detect_target")
    task.arrival_time = 4.0
    task.state = "ready"
    mask = executor.build_action_mask(state)
    assert task.state == "pending"
    assert mask.action_mask == [0, 0, 0, 0, 1]
    assert executor.advance_to_next_event(state) == []
    assert state.now == 4.0
    assert task.state == "ready"


def test_runtime_inserted_task_respects_dependencies_and_arrival():
    state, executor = make_env()
    first = executor.assign(state, "detect_target", "uav_1_rgb_sensor")
    executor.advance_to_next_event(state)
    assert state.now == first.completion_time

    incoming = deepcopy(state.get_subtask("detect_target"))
    incoming.subtask_id = "follow_up"
    incoming.state = "ready"
    incoming.arrival_time = 12.0
    incoming.deadline = 150.0
    state.add_subtask(incoming, predecessors=["detect_target"])
    assert incoming.state == "pending"
    assert executor.next_event_time(state) == 12.0

    executor.advance_to_next_event(state)
    assert incoming.state == "ready"
    assert state.now == 12.0
    assert executor.build_match_matrix(state).feasible[-1][0] == 1


def test_dynamic_insertion_rejects_unknown_and_duplicate_tasks():
    state, executor = make_env()
    incoming = deepcopy(state.get_subtask("detect_target"))
    incoming.subtask_id = "new_task"
    with pytest.raises(ValueError, match="Unknown predecessor"):
        state.add_subtask(incoming, predecessors=["nonexistent"])
    assert "new_task" not in state.task_graph.subtask_ids()
    state.add_subtask(incoming)
    with pytest.raises(ValueError, match="Duplicate subtask_id"):
        state.add_subtask(incoming)


def test_resource_failure_can_retry_on_another_uav():
    state, executor = make_env()
    second_sensor = deepcopy(state.get_resource("uav_1_rgb_sensor"))
    second_sensor.resource_id = "uav_3_rgb_sensor"
    second_sensor.owner_uav_id = "uav_3"
    second_sensor.sensing_quality = {"rgb": 0.82, "infrared": 0.76}
    state.resource_graph.resources.append(second_sensor)

    failed_attempt = executor.assign(state, "detect_target", "uav_1_rgb_sensor")
    executor.advance_time(state, 2.0)
    interrupted = executor.fail_resource(state, "uav_1_rgb_sensor", retry_task=True)

    assert interrupted == [failed_attempt]
    assert failed_attempt.status == "failed"
    assert failed_attempt.actual_end_time == pytest.approx(2.0)
    assert state.get_subtask("detect_target").state == "ready"
    assert state.get_resource("uav_1_rgb_sensor").online is False
    assert executor.build_match_matrix(state).feasible[0] == [0, 0, 1]

    result = RuleBasedScheduler(executor).run(state)
    assert result.status == "completed"
    assert result.assignments[0].resource_id == "uav_3_rgb_sensor"
    assert state.get_subtask("classify_target").state == "finished"


def test_failed_task_can_be_terminal_and_resource_restored():
    state, executor = make_env()
    executor.assign(state, "detect_target", "uav_1_rgb_sensor")
    executor.advance_time(state, 1.0)
    executor.fail_resource(state, "uav_1_rgb_sensor", retry_task=False)
    assert state.get_subtask("detect_target").state == "failed"
    assert state.get_subtask("classify_target").state == "pending"
    assert RuleBasedScheduler(executor).run(state).status == "stalled"
    executor.restore_resource(state, "uav_1_rgb_sensor")
    assert state.get_resource("uav_1_rgb_sensor").online is True
    assert state.get_subtask("detect_target").state == "failed"


def test_stale_occupied_resource_cannot_be_double_assigned():
    state, executor = make_env()
    sensor = state.get_resource("uav_1_rgb_sensor")
    sensor.occupied = True
    sensor.release_time = state.now
    assert executor.build_match_matrix(state).feasible[0][0] == 0
