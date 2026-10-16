"""第三阶段：UAV 联合动作、局部观测、全局状态及冲突处理。"""
from copy import deepcopy
from pathlib import Path

import pytest

from ubisched.graph.match_matrix import RuleBasedScorer
from ubisched.graph.resource_graph import ResourceGraph
from ubisched.graph.task_graph import TaskGraph, SubTask
from ubisched.scheduling.multi_agent_env import MultiAgentSchedulerEnv

ROOT = Path(__file__).resolve().parents[1]


def create_env(max_steps=100, max_tasks=5):
    graph = TaskGraph.from_yaml(ROOT / "configs/ubisched/task_graph_example.yaml")
    resources = ResourceGraph.from_yaml(ROOT / "configs/ubisched/resource_graph_example.yaml")
    backup = deepcopy(resources.resources[0])
    backup.resource_id = "uav_3_rgb_sensor"
    backup.owner_uav_id = "uav_3"
    backup.remaining_energy = 5000.0
    resources.resources.append(backup)
    return MultiAgentSchedulerEnv(
        graph, resources,
        RuleBasedScorer.from_yaml(ROOT / "configs/ubisched/match_scoring.yaml"),
        max_tasks=max_tasks, max_resources_per_uav=2, max_agents=4, max_steps=max_steps,
    )


def select(obs, agent, task_id, resource_id):
    return obs[agent]["action_labels"].index((task_id, resource_id))


def wait_all(env):
    return {uav: env.noop_index for uav in env.agents}


def test_fixed_dimensions_and_local_ownership():
    env = create_env()
    obs, info = env.reset()
    assert env.agents == ("uav_1", "uav_2", "uav_3")
    lengths = {u: len(env.local_vector(o)) for u, o in obs.items()}
    assert len(set(lengths.values())) == 1
    assert env.action_dim == 11
    assert all(len(o["action_mask"]) == env.action_dim for o in obs.values())
    assert all(len(o["task_features"]) == 5 for o in obs.values())
    assert all(len(o["resource_features"]) == 2 for o in obs.values())
    assert all(len(o["match_features"]) == 5 for o in obs.values())
    assert all(len(row) == 2 for o in obs.values() for row in o["match_features"])
    assert obs["uav_1"]["resource_ids"] == ["uav_1_rgb_sensor"]
    assert obs["uav_2"]["resource_ids"] == ["uav_2_compute"]
    assert obs["uav_3"]["resource_ids"] == ["uav_3_rgb_sensor"]
    assert select(obs,"uav_1","detect_target","uav_1_rgb_sensor") == 0
    assert obs["uav_2"]["action_mask"][0] == 0  # 计算节点不能检测
    assert obs["uav_3"]["action_mask"][0] == 1
    assert isinstance(info["conflicts_total"], int)
    assert len(env.state_vector()) > lengths["uav_1"]


def test_no_early_reward_and_dependency():
    env = create_env()
    obs, _ = env.reset()
    acts = wait_all(env)
    acts["uav_1"] = select(obs,"uav_1","detect_target","uav_1_rgb_sensor")
    obs, reward, done, truncated, info = env.step(acts)
    assert info["started"] == [("detect_target", "uav_1_rgb_sensor")]
    assert info["completed"] == []
    assert info["time"] == 0
    assert "completion" not in info["reward_parts"]
    assert obs["uav_2"]["action_mask"][2] == 0
    obs, reward, _, _, info = env.step(wait_all(env))
    assert "detect_target" in info["completed"]
    assert reward > 0
    assert obs["uav_2"]["action_mask"][2] == 1


def test_simultaneous_claim_conflict_not_double_assigned():
    env = create_env()
    obs,_ = env.reset()
    acts = wait_all(env)
    acts["uav_1"] = select(obs,"uav_1","detect_target","uav_1_rgb_sensor")
    acts["uav_3"] = select(obs,"uav_3","detect_target","uav_3_rgb_sensor")
    _, reward, done, truncated, info = env.step(acts)
    assert info["conflicts_this_step"] == 1
    assert info["agent_events"]["uav_3"]["status"] == "task_conflict"
    assert len(env.state.assignments) == 1
    assert env.state.get_resource("uav_3_rgb_sensor").occupied is False
    assert info["reward_parts"]["invalid_actions"] < 0


def test_two_independent_tasks_start_same_time():
    env = create_env(max_tasks=6)
    obs,_ = env.reset()
    original = env.state.get_subtask("detect_target")
    extra = deepcopy(original)
    extra.subtask_id = "detect_second"
    extra.state = "pending"
    env.add_subtask(extra)
    obs = env.observe()
    acts = wait_all(env)
    acts["uav_1"] = select(obs,"uav_1","detect_target","uav_1_rgb_sensor")
    acts["uav_3"] = select(obs,"uav_3","detect_second","uav_3_rgb_sensor")
    obs, reward, _, _, info = env.step(acts)
    assert len(info["started"]) == 2
    assert all(a.start_time == 0 for a in env.state.assignments)
    assert info["time"] == 0
    assert info["conflicts_this_step"] == 0


def test_invalid_action_does_not_mutate_and_is_penalized():
    env = create_env()
    obs, _ = env.reset()
    acts = wait_all(env)
    acts["uav_2"] = 0
    _, reward, _, _, info = env.step(acts)
    assert info["agent_events"]["uav_2"]["status"] == "invalid_action"
    assert env.state.assignments == []
    assert reward < 0


def test_wait_and_complete_episode():
    env = create_env()
    obs, _ = env.reset()
    actions = wait_all(env)
    actions["uav_1"] = 0
    obs, _, _, _, _ = env.step(actions)
    obs, _, _, _, _ = env.step(wait_all(env))
    actions = wait_all(env)
    actions["uav_2"] = 2
    obs, _, done, truncated, _ = env.step(actions)
    assert not done
    obs, _, done, truncated, info = env.step(wait_all(env))
    assert done and not truncated
    assert info["status"] == "completed"
    assert info["completion_rate"] == 1.0
    assert info["time"] == pytest.approx(9.25)


def test_reset_isolation_and_dynamic_task_padding():
    env = create_env()
    obs,_ = env.reset()
    old_local_len = len(env.local_vector(obs["uav_1"]))
    old_global_len = len(env.state_vector())
    new_task = deepcopy(env.state.get_subtask("detect_target"))
    new_task.subtask_id = "later"
    new_task.arrival_time = 12
    env.add_subtask(new_task)
    obs = env.observe()
    assert len(env.local_vector(obs["uav_1"])) == old_local_len
    assert len(env.state_vector()) == old_global_len
    assert obs["uav_1"]["task_valid"][:3] == [1,1,1]
    assert obs["uav_1"]["action_mask"][4] == 0
    obs,_ = env.reset()
    assert obs["uav_1"]["task_ids"] == ["detect_target", "classify_target"]


def test_capacity_exceeded_rejected():
    with pytest.raises(ValueError, match="exceeds max_tasks"):
        create_env(max_tasks=1)
    env = create_env(max_tasks=2)
    env.reset()
    task = deepcopy(env.state.get_subtask("detect_target"))
    task.subtask_id = "too_many"
    with pytest.raises(ValueError, match="exceeds max_tasks"):
        env.add_subtask(task)


def test_missing_agent_action_and_step_limit():
    env = create_env(max_steps=2)
    env.reset()
    with pytest.raises(ValueError, match="exactly"):
        env.step({"uav_1": env.noop_index})
    _,_,_,truncated,_ = env.step(wait_all(env))
    assert not truncated
    _,_,_,truncated,info = env.step(wait_all(env))
    assert truncated
    assert info["status"] == "step_limit"


def test_reward_published_once_and_observation_is_copy():
    env = create_env()
    obs,_ = env.reset()
    obs["uav_1"]["task_features"][0][0] = 12345
    obs["uav_1"]["action_mask"][0] = 0
    assert env.observe()["uav_1"]["action_mask"][0] == 1
    acts = wait_all(env)
    acts["uav_1"] = 0
    obs,_,_,_,_ = env.step(acts)
    obs,reward,_,_,info = env.step(wait_all(env))
    assert info["completed"] == ["detect_target"]
    assert info["reward_parts"]["completion"] > 1
    acts = wait_all(env)
    acts["uav_2"] = 2
    obs,_,_,_,info = env.step(acts)
    assert "completion" not in info["reward_parts"]
