"""Evaluation helpers for the component test scenarios."""
import random

from ubisched.experiments.evaluation import EvalMetrics, choose_rule_actions, run_episode

def run_rule_episode(*, scenario_seed: int, scenario: str, policy: str) -> EvalMetrics:
    from tests.support.scenarios import make_env
    rng = random.Random(scenario_seed + 3917)
    return run_episode(make_env(scenario_seed, scenario=scenario),
                       lambda e, obs: choose_rule_actions(e, obs, policy=policy, rng=rng),
                       policy=policy, scenario=scenario, scenario_seed=scenario_seed)

def run_mappo_episode(algo, *, scenario_seed: int, scenario: str, train_seed: int,
                      policy_name: str = "mappo_mlp"):
    """冻结模型、用与训练相同的条件采样规则作确定性测试。"""
    from tests.support.scenarios import make_env
    env = make_env(
        scenario_seed, scenario=scenario,
        deadline_features=getattr(algo, "deadline_features", False),
    )
    was_training = algo.actor.training
    algo.actor.eval()
    try:
        def action_fn(e, obs):
            _, _, actions, _ = algo.select_actions(e, obs, greedy=True)
            return dict(zip(e.agents, actions.tolist()))
        return run_episode(env, action_fn, policy=policy_name, scenario=scenario,
                           scenario_seed=scenario_seed, train_seed=train_seed)
    finally:
        algo.actor.train(was_training)
