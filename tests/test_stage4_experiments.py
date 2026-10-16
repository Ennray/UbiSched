"""阶段4：场景复现、同场景策略对比与评估指标。"""
import math
import random

import pytest

from ubisched.experiments.scenarios import build_scenario, make_env, SUPPORTED_SCENARIOS
from ubisched.experiments.evaluation import (
    POLICIES, choose_rule_actions, run_rule_episode
)


def test_scenarios_are_deterministic_and_have_dependencies():
    a, res_a, _ = build_scenario(81, scenario="staggered")
    b, res_b, _ = build_scenario(81, scenario="staggered")
    assert a == b and res_a == res_b
    assert len(a.subtasks) in (4, 6, 8)
    assert len(a.edges) * 2 == len(a.subtasks)
    assert any(x.arrival_time > 0 for x in a.subtasks) or len(a.subtasks) == 2
    assert all(x.state == "pending" for x in a.subtasks)
    assert build_scenario(81, scenario="normal")[0] != build_scenario(82, scenario="normal")[0]


def test_generated_env_dimensions_and_legal_baseline_actions():
    for scenario in SUPPORTED_SCENARIOS:
        env = make_env(31, scenario=scenario)
        obs, _ = env.reset()
        assert len(env.agents) == 3
        assert len(env.state.task_graph.subtasks) <= env.max_tasks
        for policy in POLICIES:
            chosen = choose_rule_actions(env, obs, policy=policy, rng=random.Random(123))
            assert set(chosen) == set(env.agents)
            picked = set()
            for agent, action in chosen.items():
                assert obs[agent]["action_mask"][action] == 1
                if action != env.noop_index:
                    task_id, resource_id = obs[agent]["action_labels"][action]
                    assert task_id not in picked
                    picked.add(task_id)
                    assert env.state.get_resource(resource_id).owner_uav_id == agent


def test_repeated_evaluations_match_and_no_rule_conflicts():
    for name in POLICIES:
        result1 = run_rule_episode(scenario_seed=59, scenario="normal", policy=name)
        result2 = run_rule_episode(scenario_seed=59, scenario="normal", policy=name)
        assert result1 == result2
        assert result1.total_tasks >= 4
        assert 0 <= result1.completion_rate <= 1
        assert result1.conflicts == 0
        assert math.isfinite(result1.reward)
        assert result1.deadline_met_rate <= result1.completion_rate + 1e-9


def test_invalid_scenario_and_pairs_rejected():
    with pytest.raises(ValueError):
        make_env(1, scenario="unknown")
    with pytest.raises(ValueError):
        build_scenario(1, pairs=5)


def test_mappo_eval_does_not_mutate_weights():
    torch = pytest.importorskip("torch")
    from ubisched.algorithms.mappo_baseline import MAPPOBaseline
    from ubisched.experiments.evaluation import run_mappo_episode
    torch.set_num_threads(1)
    torch.manual_seed(9)
    algo = MAPPOBaseline(make_env(1))
    before = [p.detach().clone() for p in algo.actor.parameters()]
    result = run_mappo_episode(algo, scenario_seed=100, scenario="urgent", train_seed=9)
    assert result.policy == "mappo_mlp"
    assert result.train_seed == 9
    assert all(torch.equal(a, b) for a, b in zip(before, algo.actor.parameters()))


def test_benchmark_cli_writes_reproducible_records(tmp_path):
    import csv
    import sys
    from pathlib import Path
    ROOT = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(ROOT / "scripts"))
    from run_stage4_benchmark import main
    assert main([
        "--train-episodes", "4", "--train-seeds", "3", "--eval-scenarios", "1",
        "--ppo-epochs", "1", "--output-dir", str(tmp_path)
    ]) == 0
    records = list(csv.DictReader((tmp_path / "evaluation_records.csv").open(encoding="utf-8-sig")))
    assert len(records) == len(SUPPORTED_SCENARIOS) * 4  # three rules + one MAPPO
    assert {r["policy"] for r in records} == set(POLICIES) | {"mappo_mlp"}
    assert (tmp_path / "mappo_mlp_seed_3.pt").exists()
    assert (tmp_path / "comparison_summary.csv").exists()
    assert (tmp_path / "training_log.csv").exists()
    assert (tmp_path / "experiment_config.json").exists()
