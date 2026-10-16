"""基础 MAPPO 训练测试，不需要真实 AirSim 环境。"""
import math
from pathlib import Path
import sys

import pytest

torch = pytest.importorskip("torch")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from train_mappo_baseline import make_env
from ubisched.algorithms.mappo_baseline import MAPPOBaseline


def test_actor_masks_actions_and_critic_uses_full_state():
    torch.set_num_threads(1)
    torch.manual_seed(2)
    env = make_env()
    algo = MAPPOBaseline(env)
    obs, _ = env.reset()
    with torch.no_grad():
        local = torch.tensor([env.local_vector(obs[u]) for u in env.agents])
        actions = algo.actor(local)
        assert actions.shape == (3, env.action_dim)
        mask = torch.tensor([obs[u]["action_mask"] for u in env.agents], dtype=torch.bool)
        assert torch.all(torch.isfinite(actions))
        global_state = torch.tensor(env.state_vector())
        assert algo.critic(global_state).shape == (1,)
        for _ in range(20):
            picked = torch.distributions.Categorical(
                logits=actions.masked_fill(~mask, -1e9)
            ).sample()
            assert all(mask[i, picked[i]] for i in range(3))


def test_mappo_training_changes_parameters_and_losses_finite():
    torch.set_num_threads(1)
    torch.manual_seed(7)
    env = make_env()
    algo = MAPPOBaseline(env, lr=1e-3)
    before_actor = [p.detach().clone() for p in algo.actor.parameters()]
    before_critic = [p.detach().clone() for p in algo.critic.parameters()]
    eps = [algo.sample_episode(make_env()) for _ in range(3)]
    assert all(0 <= ep.completion_rate <= 1 for ep in eps)
    assert all(len(ep.transitions) > 0 for ep in eps)
    m = algo.update(eps, epochs=2)
    assert all(math.isfinite(m[k]) for k in ("actor_loss", "critic_loss", "entropy"))
    assert any(not torch.equal(a,b) for a,b in zip(before_actor,algo.actor.parameters()))
    assert any(not torch.equal(a,b) for a,b in zip(before_critic,algo.critic.parameters()))
    ep = algo.sample_episode(make_env(), greedy=True)
    assert len(ep.transitions) > 0


def test_ppo_works_with_step_limit_bootstrap():
    torch.set_num_threads(1)
    torch.manual_seed(9)
    env = make_env()
    env._base.max_steps = 1
    algo = MAPPOBaseline(env)
    episode = algo.sample_episode(env)
    assert episode.status == "step_limit"
    assert math.isfinite(episode.bootstrap_value)
    metrics = algo.update([episode], epochs=1)
    assert metrics["samples"] == 1
