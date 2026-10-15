"""第二阶段：训练环境接口、动作掩码、奖励和事件推进的回归测试。"""
from copy import deepcopy
from pathlib import Path

import pytest

from ubisched.graph.match_matrix import RuleBasedScorer
from ubisched.graph.resource_graph import ResourceGraph
from ubisched.graph.task_graph import SubTask, TaskGraph
from ubisched.scheduling.scheduler_env import RewardConfig, SchedulerEnv

ROOT = Path(__file__).resolve().parents[1]


def make_env(**kwargs):
    task_graph = TaskGraph.from_yaml(ROOT / "configs/ubisched/task_graph_example.yaml")
    resource_graph = ResourceGraph.from_yaml(ROOT / "configs/ubisched/resource_graph_example.yaml")
    scorer = RuleBasedScorer.from_yaml(ROOT / "configs/ubisched/match_scoring.yaml")
    return SchedulerEnv(task_graph, resource_graph, scorer, **kwargs)


def test_reset_exposes_action_labels_features_and_correct_mask():
    env = make_env()
    obs, info = env.reset()
    assert obs["task_ids"] == ["detect_target", "classify_target"]
    assert obs["resource_ids"] == ["uav_1_rgb_sensor", "uav_2_compute"]
    assert obs["action_mask"] == [1, 0, 0, 0, 1]
    assert obs["noop_index"] == 4
    assert obs["action_labels"][0] == "assign(detect_target, uav_1_rgb_sensor)"
    assert len(obs["task_features"]) == 2
    assert len(obs["resource_features"]) == 2
    assert len(obs["match_features"]) == 2
    assert len(obs["match_features"][0][0]) == 7
    assert info["completion_rate"] == 0.0


def test_steps_advance_state_and_rewards_are_paid_on_completion():
    env = make_env()
    env.reset()
    obs, reward, terminated, truncated, info = env.step(0)
    assert info["started"] == ("detect_target", "uav_1_rgb_sensor")
    assert info["completed"] == []
    assert reward < 0  # 只有能耗罚分，没有提前发放完成收益
    assert env.state.now == 0.0
    assert env.state.get_resource("uav_1_rgb_sensor").occupied
    assert obs["action_mask"] == [0, 0, 0, 0, 1]
    assert not terminated and not truncated

    obs, reward, terminated, truncated, info = env.step(obs["noop_index"])
    assert info["completed"] == ["detect_target"]
    assert reward > 0  # 检测真正结束时才给完成奖励
    assert env.state.now == pytest.approx(5.0)
    assert obs["action_mask"] == [0, 0, 0, 1, 1]
    assert not terminated and not truncated

    obs, reward, terminated, truncated, info = env.step(3)
    assert info["started"] == ("classify_target", "uav_2_compute")
    assert info["completed"] == []
    obs, reward, terminated, truncated, info = env.step(obs["noop_index"])
    assert terminated and not truncated
    assert info["status"] == "completed"
    assert info["completion_rate"] == 1.0
    assert info["deadline_met_rate"] == 1.0
    assert env.state.now == pytest.approx(9.25)
    with pytest.raises(RuntimeError, match="Episode has ended"):
        env.step(0)


def test_invalid_actions_do_not_modify_resources_or_start_tasks():
    env = make_env()
    env.reset()
    energy = env.state.get_resource("uav_1_rgb_sensor").remaining_energy
    for invalid in (1, 999, -1):
        _, reward, terminated, truncated, info = env.step(invalid)
        assert info["reason"] == "invalid_action"
        assert reward == pytest.approx(-0.5)
        assert not terminated and not truncated
        assert env.state.assignments == []
    assert env.state.get_resource("uav_1_rgb_sensor").remaining_energy == energy


def test_noop_waits_until_future_task_arrives():
    env = make_env()
    env._initial_tasks.get_subtask("detect_target").arrival_time = 8.0
    obs, _ = env.reset()
    assert obs["action_mask"] == [0, 0, 0, 0, 1]
    obs, reward, _, _, info = env.step(obs["noop_index"])
    assert info["reason"] == "wait_for_event"
    assert info["elapsed_time"] == pytest.approx(8.0)
    assert env.state.now == pytest.approx(8.0)
    assert reward < 0
    assert obs["action_mask"][0] == 1


def test_noop_without_future_event_does_not_falsely_advance_time():
    env = make_env(max_steps=2)
    obs, _ = env.reset()
    for i in range(2):
        obs, reward, terminated, truncated, info = env.step(obs["noop_index"])
        assert info["reason"] == "no_future_event"
        assert reward < 0
        assert env.state.now == 0
    assert truncated and not terminated
    assert info["status"] == "step_limit"


def test_stalled_detected_without_event_or_feasible_action():
    env = make_env()
    for r in env._initial_resources.resources:
        r.remaining_energy = 0.0
    obs, _ = env.reset()
    assert obs["action_mask"] == [0, 0, 0, 0, 1]
    _, reward, terminated, truncated, info = env.step(obs["noop_index"])
    assert terminated and not truncated
    assert info["status"] == "stalled"
    assert reward == pytest.approx(-1.0)


def test_reset_does_not_leak_state_across_episodes():
    env = make_env()
    initial, _ = env.reset()
    env.step(0)
    fresh, info = env.reset(seed=777)
    assert fresh["action_mask"] == initial["action_mask"]
    assert env.state.assignments == []
    assert env.state.get_resource("uav_1_rgb_sensor").occupied is False
    assert env.steps == 0


def test_adding_new_task_expands_observation_and_action_map():
    env = make_env()
    env.reset()
    incoming = deepcopy(env.state.get_subtask("detect_target"))
    incoming.subtask_id = "follow_up"
    incoming.arrival_time = 12.0
    env.add_subtask(incoming, predecessors=["detect_target"])
    obs = env.observe()
    assert len(obs["task_ids"]) == 3
    assert len(obs["action_mask"]) == 7
    assert obs["noop_index"] == 6
    assert obs["action_mask"] == [1, 0, 0, 0, 0, 0, 1]


def test_two_ready_tasks_can_be_assigned_without_advance_time():
    env = make_env()
    obs, _ = env.reset()
    extra_res = deepcopy(env.state.get_resource("uav_1_rgb_sensor"))
    extra_res.resource_id = "uav_3_rgb_sensor"
    env.state.resource_graph.resources.append(extra_res)
    extra_task = deepcopy(env.state.get_subtask("detect_target"))
    extra_task.subtask_id = "extra_detect"
    env.add_subtask(extra_task)
    obs = env.observe()
    assert obs["action_mask"] == [1, 0, 1, 0, 0, 0, 1, 0, 1, 1]
    obs, *_ = env.step(0)  # detect -> UAV1
    assert env.state.now == 0.0
    assert obs["action_mask"][8] == 1
    obs, *_ = env.step(8)  # extra_detect -> UAV3
    assert env.state.now == 0.0
    assert len(env.state.active_assignments()) == 2


def test_zero_duration_task_finishes_immediately():
    env = make_env()
    t = env._initial_tasks.get_subtask("detect_target")
    t.task_type = "compute"
    t.required_modalities_any = []
    t.compute_cycles = 0
    t.data_size = 0
    env._initial_tasks.edges.clear()
    env._initial_tasks.subtasks = [t]
    cpu = env._initial_resources.resources[1]
    cpu.resource_id = "zero_compute"
    cpu.power = 0
    env._initial_resources.resources = [cpu]
    obs, _ = env.reset()
    assert obs["action_mask"] == [1, 1]
    obs, reward, terminated, truncated, info = env.step(0)
    assert terminated and not truncated
    assert info["completed"] == ["detect_target"]
    assert reward > 0
    assert env.state.now == 0.0
    assert env.state.get_resource("zero_compute").occupied is False


def test_failure_event_blocks_failed_resource_and_allows_backup():
    env = make_env()
    obs, _ = env.reset()
    spare = deepcopy(env.state.get_resource("uav_1_rgb_sensor"))
    spare.resource_id = "backup"
    env.state.resource_graph.resources.append(spare)
    obs = env.observe()
    env.step(0)
    failures = env.fail_resource("uav_1_rgb_sensor")
    assert len(failures) == 1
    assert env.state.get_subtask("detect_target").state == "ready"
    obs = env.observe()
    assert obs["action_mask"] == [0, 0, 1, 0, 0, 0, 1]
    assert env.state.assignments[0].status == "failed"


def test_reward_weights_can_be_configured():
    env = make_env(reward_config=RewardConfig(invalid_action=-3.0))
    env.reset()
    _, reward, *_ = env.step(1)
    assert reward == -3.0


def test_requires_reset_and_valid_max_steps():
    env = make_env()
    with pytest.raises(RuntimeError, match="reset"):
        env.observe()
    with pytest.raises(ValueError, match="max_steps"):
        make_env(max_steps=0)


def test_completion_reward_includes_predicted_quality():
    env = make_env(
        reward_config=RewardConfig(
            completion=0, on_time_bonus=0, priority_bonus=0,
            quality_bonus=2.0, energy_cost=0, elapsed_time_cost=0,
        )
    )
    obs, _ = env.reset()
    obs, reward, _, _, info = env.step(0)
    assert reward == 0.0
    obs, reward, _, _, info = env.step(obs["noop_index"])
    assert reward == pytest.approx(2.0 * 0.85)
    assert env.state.assignments[0].estimated_quality == pytest.approx(0.85)
