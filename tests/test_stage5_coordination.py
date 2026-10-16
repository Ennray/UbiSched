"""阶段5：PPO联合动作条件分布、截止时间压力与消融运行。"""
import math
import pytest

torch = pytest.importorskip("torch")

from ubisched.algorithms.mappo_baseline import MAPPOBaseline
from ubisched.experiments.scenarios import make_env
from ubisched.experiments.evaluation import run_mappo_episode


def test_coordinated_joint_actions_never_claim_same_task():
    torch.set_num_threads(1)
    torch.manual_seed(6)
    env = make_env(6, scenario="urgent")
    algo = MAPPOBaseline(env, coordinate_actions=True)
    obs, _ = env.reset()
    for _ in range(30):
        _, masks, actions, logprobs = algo.select_actions(env, obs)
        task_ids = []
        for idx, agent in enumerate(env.agents):
            action = int(actions[idx])
            assert masks[idx, action]
            assert math.isfinite(logprobs[idx].item())
            if action != env.noop_index:
                task_ids.append(obs[agent]["action_labels"][action][0])
        assert len(task_ids) == len(set(task_ids))
    ep = algo.sample_episode(make_env(6, scenario="urgent"))
    assert ep.conflicts == 0
    result = algo.update([ep], epochs=2)
    assert math.isfinite(result["actor_loss"])


def test_deadline_features_compatible_with_critic_and_ppo():
    torch.set_num_threads(1)
    env = make_env(17, scenario="urgent", deadline_features=True)
    obs, _ = env.reset()
    assert all(len(v["urgency_features"]) == env.noop_index for v in obs.values())
    assert any(any(v["urgency_features"]) for v in obs.values())
    basic = make_env(17, scenario="urgent")
    basic_obs, _ = basic.reset()
    assert len(env.local_vector(obs[env.agents[0]])) == len(basic.local_vector(basic_obs[basic.agents[0]])) + env.noop_index
    assert len(env.state_vector()) == len(basic.state_vector()) + env.noop_index * env.max_agents
    algo = MAPPOBaseline(env, coordinate_actions=True)
    episode = algo.sample_episode(env)
    assert episode.conflicts == 0
    assert math.isfinite(algo.update([episode], epochs=1)["critic_loss"])
    result = run_mappo_episode(algo, scenario_seed=500004, scenario="urgent", train_seed=17,
                               policy_name="mappo_coordinated_urgency")
    assert result.conflicts == 0


def test_original_policy_stays_compatible_with_stage4():
    torch.set_num_threads(1)
    torch.manual_seed(7)
    basic = MAPPOBaseline(make_env(7), coordinate_actions=False)
    result = run_mappo_episode(basic, scenario_seed=500001, scenario="normal", train_seed=7)
    assert result.policy == "mappo_mlp"
    assert result.attempted_conflicts == result.conflicts


def test_stage5_cli_exports_diagnostics(tmp_path):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from run_stage5_diagnostics import main
    assert main(["--train-episodes", "3", "--eval-scenarios", "1", "--ppo-epochs", "1",
                 "--output-dir", str(tmp_path)]) == 0
    import csv
    with (tmp_path / "comparison_summary.csv").open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 3 * (3 + 4)
    assert "avoidable_wait_steps_mean" in rows[0]
    assert (tmp_path / "mappo_coordinated_urgency_seed_11.pt").exists()


def test_work_conserving_mask_has_consistent_action_logprob():
    torch.set_num_threads(1)
    from torch import nn

    class AlwaysWait(nn.Module):
        def __init__(self, n):
            super().__init__()
            self.n = n
        def forward(self, x):
            result = torch.zeros(x.shape[0], self.n)
            result[:, -1] = 1000.0
            return result

    env = make_env(13, scenario="urgent", deadline_features=True)
    algo = MAPPOBaseline(env, coordinate_actions=True, work_conserving=True)
    algo.actor = AlwaysWait(env.action_dim)
    obs, _ = env.reset()
    inputs, masks, actions, logprobs = algo.select_actions(env, obs, greedy=True)
    assert any(int(a) != env.noop_index for a in actions)
    assert all(torch.isfinite(logprobs))
    assert all(bool(masks[i, actions[i]]) for i in range(len(env.agents)))
    # 只要可以分配任务，团队不可以全体无意义等待。
    ep = algo.sample_episode(env, greedy=True)
    assert ep.completion_rate >= 0.0
    assert ep.conflicts == 0
