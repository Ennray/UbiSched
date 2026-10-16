"""第6步：注意力策略、padding、序列排列、PPO条件概率和变化UAV数。"""
import math
import torch

from ubisched.algorithms.transformer_mappo import TransformerMAPPO
from ubisched.experiments.scenarios import make_env, build_scenario
from ubisched.scheduling.multi_agent_env import MultiAgentSchedulerEnv


def _model_env(seed=42, *, pairs=2, num_uavs=3):
    return make_env(seed, pairs=pairs, num_uavs=num_uavs, deadline_features=True)


def test_attention_training_and_exact_ppo_probability():
    torch.set_num_threads(1)
    torch.manual_seed(7)
    algo = TransformerMAPPO(_model_env(), hidden=32, heads=4, layers=1)
    env = _model_env(19, pairs=3)
    obs, _ = env.reset()
    features, masks, actions, logprobs = algo.select_actions(env, obs)
    assert features.shape[0] == 3
    assert all(masks[i, actions[i]] for i in range(3))
    assert all(torch.isfinite(logprobs))
    inputs = algo._make_actor_inputs(env, obs)
    logits = algo.actor(inputs).masked_fill(~masks, -1e9)
    recomputed = torch.distributions.Categorical(logits=logits).log_prob(actions)
    assert torch.allclose(recomputed, logprobs, atol=1e-5)
    initial = [p.detach().clone() for p in algo.actor.parameters()]
    episodes = [algo.sample_episode(_model_env(seed, pairs=(seed % 3 + 2))) for seed in (11, 12, 13)]
    results = algo.update(episodes, epochs=2)
    assert all(math.isfinite(results[k]) for k in ("critic_loss", "actor_loss", "entropy"))
    assert any(not torch.equal(p, v) for p, v in zip(initial, algo.actor.parameters()))
    assert all(ep.conflicts == 0 for ep in episodes)


def test_padding_does_not_affect_valid_task_resource_logits():
    torch.manual_seed(15)
    tasks, resources, scorer = build_scenario(17, pairs=2)
    env = MultiAgentSchedulerEnv(tasks, resources, scorer, max_tasks=8,
                                 max_resources_per_uav=2, max_agents=3,
                                 include_deadline_features=True)
    algo = TransformerMAPPO(env, hidden=32, heads=4, layers=1)
    obs, _ = env.reset()
    inputs = algo._make_actor_inputs(env, obs)
    with torch.no_grad():
        output = algo.actor(inputs)
        altered = {k: v.clone() for k, v in inputs.items()}
        altered["tasks"][:, 4:, :] = 100000.0
        altered["resources"][:, 1, :] = -99999.0
        new_output = algo.actor(altered)
    # 4个真实任务，每架UAV只有1个真实资源：只比较合法槽与等待动作。
    for idx in range(4):
        action = idx * 2
        assert torch.allclose(output[:, action], new_output[:, action], atol=1e-5)
    assert torch.allclose(output[:, -1], new_output[:, -1], atol=1e-5)


def test_task_token_permutation_equivariance():
    torch.manual_seed(12)
    env = _model_env(15)
    algo = TransformerMAPPO(env, hidden=32, heads=4, layers=1)
    obs, _ = env.reset()
    inputs = algo._make_actor_inputs(env, obs)
    order = torch.tensor([1, 0, 3, 2, 4, 5, 6, 7])
    shuffled = {k: v.clone() for k, v in inputs.items()}
    for key in ("tasks", "task_valid", "pairs", "urgency"):
        shuffled[key] = shuffled[key][:, order]
    with torch.no_grad():
        original = algo.actor(inputs).reshape(3, -1)
        shuffled_scores = algo.actor(shuffled).reshape(3, -1)
    original_pairs = original[:, :-1].reshape(3, 8, 1)
    shuffled_pairs = shuffled_scores[:, :-1].reshape(3, 8, 1)
    assert torch.allclose(shuffled_pairs, original_pairs[:, order], atol=2e-5)
    assert torch.allclose(shuffled_scores[:, -1], original[:, -1], atol=2e-5)


def test_evaluate_on_two_uavs_without_rebuilding_weights():
    torch.manual_seed(3)
    algo = TransformerMAPPO(_model_env(20, num_uavs=3),
                            hidden=32, heads=4, layers=1)
    env = _model_env(21, num_uavs=2, pairs=1)
    obs, _ = env.reset()
    _, masks, actions, _ = algo.select_actions(env, obs, greedy=True)
    assert actions.shape == (2,)
    assert all(masks[i, actions[i]] for i in range(2))
    result = algo.sample_episode(env, greedy=True)
    assert 0 <= result.completion_rate <= 1


def test_stage6_cli_exports_and_checkpoints(tmp_path):
    from pathlib import Path
    import sys
    import csv
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
    from run_stage6_transformer import main
    assert main(['--train-episodes', '3', '--eval-scenarios', '1',
                 '--ppo-epochs', '1', '--hidden', '32', '--heads', '4',
                 '--layers', '1', '--output-dir', str(tmp_path)]) == 0
    with (tmp_path / 'comparison_summary.csv').open(encoding='utf-8-sig') as f:
        data = list(csv.DictReader(f))
    assert len(data) == 6 * (3 + 2)
    assert any(row['scenario'] == 'urgent_2uav' for row in data)
    assert (tmp_path / 'mappo_transformer_seed_11.pt').exists()
    assert (tmp_path / 'mappo_mlp_seed_11.pt').exists()
    import json
    progress = json.loads((tmp_path / 'experiment_progress.json').read_text())
    assert progress['complete'] is True
