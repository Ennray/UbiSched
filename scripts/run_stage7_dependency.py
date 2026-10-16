"""第七阶段：DAG依赖增强Transformer与第六阶段Transformer公平对比。

两者使用完全相同的任务图、训练序列、Actor之外的PPO参数及Critic结构。
额外评测带分叉/汇合依赖的任务图，并使用未见过的独立测试种子。
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import random
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ubisched.algorithms.transformer_mappo import (
    DependencyAwareTransformerMAPPO, TransformerMAPPO,
)
from ubisched.experiments.evaluation import POLICIES, choose_rule_actions, run_episode
from ubisched.experiments.scenarios import STAGE7_SCENARIOS, make_env
from run_stage6_transformer import summarize, write_csv


def evaluate(policy, scenario, scenario_seed, num_uavs, *, algo=None, train_seed=None):
    env = make_env(scenario_seed, scenario=scenario, num_uavs=num_uavs,
                   deadline_features=True, dependency_features=True)
    if algo is None:
        rng = random.Random(scenario_seed + 3917)

        def action_fn(environment, obs):
            return choose_rule_actions(environment, obs, policy=policy, rng=rng)
    else:
        def action_fn(environment, obs):
            _, _, actions, _ = algo.select_actions(environment, obs, greedy=True)
            return {name: int(actions[i]) for i, name in enumerate(environment.agents)}
    label = scenario if num_uavs == 3 else f"{scenario}_2uav"
    return run_episode(env, action_fn, policy=policy, scenario=label,
                       scenario_seed=scenario_seed, train_seed=train_seed).to_dict()


def main(argv=None):
    parser = argparse.ArgumentParser(description="UbiSched stage7 task-dependency benchmark")
    parser.add_argument('--train-episodes', type=int, default=120)
    parser.add_argument('--train-seeds', default='11')
    parser.add_argument('--eval-scenarios', type=int, default=12)
    parser.add_argument('--batch-size', type=int, default=4)
    parser.add_argument('--ppo-epochs', type=int, default=3)
    parser.add_argument('--hidden', type=int, default=64)
    parser.add_argument('--heads', type=int, default=4)
    parser.add_argument('--layers', type=int, default=2)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'outputs/stage7')
    args = parser.parse_args(argv)
    if min(args.train_episodes, args.eval_scenarios, args.batch_size,
           args.ppo_epochs, args.hidden, args.heads, args.layers) <= 0:
        parser.error('All numeric options must be positive')
    if args.hidden % args.heads:
        parser.error('--hidden must be divisible by --heads')
    seeds = [int(s.strip()) for s in args.train_seeds.split(',') if s.strip()]
    if len(set(seeds)) != len(seeds) or not seeds:
        parser.error('--train-seeds must be distinct integers')
    import torch
    torch.set_num_threads(1)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    training = []
    evaluation = []
    completed_models = []
    cases = [(scenario, n_uavs, 700000 + s_index * 10000 + (3 - n_uavs) * 100000 + j)
             for n_uavs in (3, 2)
             for s_index, scenario in enumerate(STAGE7_SCENARIOS)
             for j in range(args.eval_scenarios)]
    config = {
        'training_scenarios': STAGE7_SCENARIOS,
        'evaluation_scenarios': STAGE7_SCENARIOS,
        'training_seed_list': seeds,
        'train_episodes_per_seed': args.train_episodes,
        'independent_eval_cases_per_scenario_and_uav_count': args.eval_scenarios,
        'training_uav_count': 3, 'evaluation_uav_counts': [3,2],
        'batch_size': args.batch_size, 'ppo_epochs': args.ppo_epochs,
        'hidden': args.hidden, 'heads': args.heads, 'layers': args.layers,
        'strategies': ['transformer_v6', 'dependency_transformer_v7', *POLICIES],
        'note': '同种子同场景同训练预算。环境为预估时延模拟器，非AirSim实测；两Actor参数量不同。',
    }
    (args.output_dir / 'experiment_config.json').write_text(
        json.dumps(config, indent=2, ensure_ascii=False), encoding='utf-8')

    def save_progress(complete=False):
        write_csv(args.output_dir / 'training_log.csv', training)
        write_csv(args.output_dir / 'evaluation_records.csv', evaluation)
        write_csv(args.output_dir / 'comparison_summary.csv', summarize(evaluation))
        (args.output_dir / 'progress.json').write_text(json.dumps(
            {'completed_models': completed_models, 'complete': complete,
             'expected_models': len(seeds) * 2}, ensure_ascii=False, indent=2),
            encoding='utf-8')

    for scenario, n_uavs, scenario_seed in cases:
        for policy in POLICIES:
            evaluation.append(evaluate(policy, scenario, scenario_seed, n_uavs))
    save_progress()
    for seed in seeds:
        rng = random.Random(seed)
        schedule = [(rng.randrange(0, 500000), rng.choice(STAGE7_SCENARIOS))
                    for _ in range(args.train_episodes)]
        for kind, model_class in (
            ('transformer_v6', TransformerMAPPO),
            ('dependency_transformer_v7', DependencyAwareTransformerMAPPO),
        ):
            random.seed(seed)
            torch.manual_seed(seed)
            reference = make_env(seed, deadline_features=True, dependency_features=True)
            algo = model_class(reference, hidden=args.hidden, heads=args.heads,
                               layers=args.layers, coordinate_actions=True,
                               work_conserving=True)
            for offset in range(0, len(schedule), args.batch_size):
                batch = schedule[offset: offset + args.batch_size]
                episodes = [algo.sample_episode(make_env(s, scenario=scenario,
                            deadline_features=True, dependency_features=True))
                            for s, scenario in batch]
                metrics = algo.update(episodes, epochs=args.ppo_epochs)
                training.append({
                    'policy': kind, 'train_seed': seed, 'episodes': offset + len(batch),
                    'reward_mean': statistics.mean(e.team_reward for e in episodes),
                    'completion_rate_mean': statistics.mean(e.completion_rate for e in episodes),
                    'conflicts_mean': statistics.mean(e.conflicts for e in episodes),
                    **metrics,
                })
            torch.save({
                'actor': algo.actor.state_dict(), 'critic': algo.critic.state_dict(),
                'actor_type': algo.actor_kind, 'architecture': algo.architecture,
                'train_seed': seed, 'train_episodes': args.train_episodes,
                'include_dependency_features': True,
                'include_deadline_features': True,
                'coordinate_actions': True, 'work_conserving': True,
            }, args.output_dir / f'{kind}_seed_{seed}.pt')
            algo.actor.eval()
            for scenario, n_uavs, scenario_seed in cases:
                evaluation.append(evaluate(kind, scenario, scenario_seed, n_uavs,
                                           algo=algo, train_seed=seed))
            completed_models.append({'strategy': kind, 'seed': seed})
            save_progress()
            print(f"已完成 {kind} seed={seed} 训练={args.train_episodes}局", flush=True)
    save_progress(complete=True)
    for item in summarize(evaluation):
        if item['scenario'] in ('dependency', 'urgent'):
            print(item['policy'], item['scenario'],
                  f"完成率={item['completion_rate_mean']:.1%}",
                  f"截止时间满足率={item['deadline_met_rate_mean']:.1%}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
