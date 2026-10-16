"""第七阶段：任务DAG特征、消息传递、动态新增、训练概率一致性。"""
from copy import deepcopy
import math

import pytest

torch = pytest.importorskip("torch")

from ubisched.graph.dependency_features import build_dependency_features
from ubisched.graph.task_graph import TaskEdge
from ubisched.experiments.scenarios import build_scenario, make_env
from ubisched.algorithms.transformer_mappo import (
    DependencyAwareTransformerMAPPO, TransformerMAPPO,
)


def _env(seed=20, *, pairs=3, scenario="dependency"):
    return make_env(seed, scenario=scenario, pairs=pairs,
                    deadline_features=True, dependency_features=True)


def test_dependency_features_include_fork_join_and_unfinished_descendants():
    graph, _, _ = build_scenario(20, scenario="dependency", pairs=3)
    features, adj = build_dependency_features(graph, 0, 8)
    ids = graph.subtask_ids()
    i = ids.index("detect_0")
    a, b = ids.index("classify_0"), ids.index("classify_1")
    assert adj[i][a] == 1 and adj[i][b] == 1
    assert features[i][0] == pytest.approx(2 / 8)
    assert features[i][1] == pytest.approx(2 / 8)
    graph.get_subtask("classify_1").state = "finished"
    after, _ = build_dependency_features(graph, 0, 8)
    assert after[i][0] == pytest.approx(1 / 8)
    assert after[i][1] == pytest.approx(1 / 8)
    assert len(after) == 8 and len(adj) == 8 and len(adj[-1]) == 8


def test_dependency_graph_rejects_cycles_and_missing_nodes():
    graph, _, _ = build_scenario(18, scenario="dependency", pairs=2)
    graph.edges.append(TaskEdge("classify_0", "detect_0"))
    with pytest.raises(ValueError, match="cycle"):
        build_dependency_features(graph, 0, 8)
    graph.edges.pop()
    graph.edges.append(TaskEdge("nonexistent", "detect_0"))
    with pytest.raises(ValueError, match="unknown task"):
        build_dependency_features(graph, 0, 8)


def test_online_added_task_updates_graph_features_without_reinitialization():
    env = _env(20, pairs=2)
    obs, _ = env.reset()
    agent = env.agents[0]
    prev = obs[agent]["dependency_features"]
    added = deepcopy(env.state.task_graph.get_subtask("classify_0"))
    added.subtask_id = "classify_added"
    added.arrival_time = 5.0
    env.add_subtask(added, predecessors=["detect_0"])
    obs2 = env.observe()
    ids = obs2[agent]["task_ids"]
    assert len(ids) == 5
    assert obs2[agent]["dependency_matrix"][ids.index("detect_0")][ids.index("classify_added")] == 1
    assert obs2[agent]["dependency_features"][ids.index("detect_0")][0] > prev[ids.index("detect_0")][0]
    assert obs2[agent]["action_mask"][ids.index("classify_added")] == 0
    assert sum(obs2[agent]["task_valid"]) == 5


def test_graph_model_logits_react_to_edges_and_downstream_features():
    torch.set_num_threads(1)
    torch.manual_seed(13)
    env = _env(20)
    algo = DependencyAwareTransformerMAPPO(env, hidden=32, layers=1, heads=4)
    obs, _ = env.reset()
    original = algo._make_actor_inputs(env, obs)
    modified = {name: value.clone() for name, value in original.items()}
    modified["dependency_matrix"].zero_()
    modified["dependency_features"].zero_()
    with torch.no_grad():
        original_logits = algo.actor(original)
        modified_logits = algo.actor(modified)
    assert not torch.allclose(original_logits, modified_logits, atol=1e-6)


def test_graph_task_permutation_and_padding_consistency():
    torch.set_num_threads(1)
    torch.manual_seed(14)
    env = _env(21, pairs=2)
    algo = DependencyAwareTransformerMAPPO(env, hidden=32, layers=1, heads=4)
    obs, _ = env.reset()
    inputs = algo._make_actor_inputs(env, obs)
    order = torch.tensor([1, 0, 3, 2, 4, 5, 6, 7])
    shuffled = {key: value.clone() for key, value in inputs.items()}
    for key in ("tasks", "task_valid", "pairs", "urgency", "dependency_features"):
        shuffled[key] = shuffled[key][:, order]
    shuffled["dependency_matrix"] = shuffled["dependency_matrix"][:, order][:, :, order]
    dirty = {key: value.clone() for key, value in inputs.items()}
    dirty["dependency_features"][:, 4:] = -5000.0
    dirty["dependency_matrix"][:, 4:, :] = 1
    dirty["dependency_matrix"][:, :, 4:] = 1
    with torch.no_grad():
        base = algo.actor(inputs)
        permuted = algo.actor(shuffled)
        padding = algo.actor(dirty)
    assert torch.allclose(permuted[:, :-1].reshape(3, 8, 1),
                          base[:, :-1].reshape(3, 8, 1)[:, order], atol=3e-5)
    assert torch.allclose(base[:, -1], permuted[:, -1], atol=3e-5)
    for idx in range(4):
        assert torch.allclose(base[:, idx], padding[:, idx], atol=3e-5)
    assert torch.allclose(base[:, -1], padding[:, -1], atol=3e-5)


def test_graph_model_ppo_update_and_log_prob():
    torch.set_num_threads(1)
    torch.manual_seed(16)
    env = _env(22)
    algo = DependencyAwareTransformerMAPPO(env, hidden=32, layers=1, heads=4)
    obs, _ = env.reset()
    features, masks, actions, old_log_probs = algo.select_actions(env, obs)
    with torch.no_grad():
        recomputed = torch.distributions.Categorical(
            logits=algo.actor(algo._make_actor_inputs(env, obs)).masked_fill(~masks, -1e9)
        ).log_prob(actions)
    assert torch.allclose(recomputed, old_log_probs, atol=1e-5)
    initial = [v.detach().clone() for v in algo.actor.parameters()]
    episodes = [algo.sample_episode(_env(s)) for s in (20, 22, 24)]
    stats = algo.update(episodes, epochs=2)
    assert all(math.isfinite(stats[key]) for key in ("actor_loss", "critic_loss", "entropy"))
    assert any(not torch.equal(v, initial[i]) for i,v in enumerate(algo.actor.parameters()))
    assert all(e.conflicts == 0 for e in episodes)
    with pytest.raises(ValueError, match="dependency"):
        algo.select_actions(make_env(20, deadline_features=True),
                            make_env(20, deadline_features=True).reset()[0])


def test_same_env_old_transformer_ignores_extra_dependency_fields():
    torch.set_num_threads(1)
    env = _env(19)
    old = TransformerMAPPO(env, hidden=32, layers=1, heads=4)
    obs, _ = env.reset()
    a = old._make_actor_inputs(env, obs)
    b = {k:v for k,v in a.items() if not k.startswith('dependency_')}
    with torch.no_grad():
        assert torch.equal(old.actor(a), old.actor(b))


def test_stage7_cli_export_and_common_eval_cases(tmp_path):
    import csv
    import json
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
    from run_stage7_dependency import main
    assert main(['--train-episodes', '2', '--eval-scenarios', '1',
                 '--ppo-epochs', '1', '--hidden', '32', '--heads', '4',
                 '--layers', '1', '--output-dir', str(tmp_path)]) == 0
    with (tmp_path / 'comparison_summary.csv').open(encoding='utf-8-sig') as f:
        summary = list(csv.DictReader(f))
    assert len(summary) == (3+2)*4*2
    assert (tmp_path / 'dependency_transformer_v7_seed_11.pt').exists()
    assert (tmp_path / 'transformer_v6_seed_11.pt').exists()
    with (tmp_path / 'evaluation_records.csv').open(encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    newer = {r['scenario_seed'] for r in rows if r['policy']=='dependency_transformer_v7'}
    older = {r['scenario_seed'] for r in rows if r['policy']=='transformer_v6'}
    assert newer == older
    assert json.loads((tmp_path / 'progress.json').read_text())['complete']
