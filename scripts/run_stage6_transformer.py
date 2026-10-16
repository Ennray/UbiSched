"""第六阶段：同训练预算比较MLP与任务资源Transformer。

同样环境、随机种子、场景、规则和PPO更新；额外检查2 UAV数量变化的测试场景。
训练/测试严格分离，单种子数字不可作为论文结论。
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

from ubisched.algorithms.mappo_baseline import MAPPOBaseline
from ubisched.algorithms.transformer_mappo import TransformerMAPPO
from ubisched.experiments.evaluation import (
    POLICIES, choose_rule_actions, run_episode,
)
from ubisched.experiments.scenarios import SUPPORTED_SCENARIOS, make_env


def write_csv(path, records):
    if not records:
        return
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def summarize(records):
    grouped = {}
    for row in records:
        key = (row['policy'], row['scenario'], row['train_seed'])
        grouped.setdefault(key, []).append(row)
    result = []
    for (policy, scenario, seed), rows in sorted(grouped.items()):
        item = {'policy': policy, 'scenario': scenario,
                'train_seed': seed, 'samples': len(rows)}
        for metric in ('completion_rate','deadline_met_rate','reward','total_energy',
                       'conflicts','avoidable_wait_steps','decisions'):
            vals = [float(r[metric]) for r in rows]
            item[f'{metric}_mean'] = statistics.mean(vals)
            item[f'{metric}_std'] = statistics.stdev(vals) if len(vals) > 1 else 0.0
        result.append(item)
    return result


def eval_once(*, policy, variant, seed, actual_scenario, num_uavs, algo=None,
              train_seed=None):
    env = make_env(seed, scenario=actual_scenario, deadline_features=True,
                   num_uavs=num_uavs)
    scenario_label = actual_scenario if num_uavs == 3 else actual_scenario + '_2uav'
    if algo is None:
        rng = random.Random(seed + 3917)
        fn = lambda e, obs: choose_rule_actions(e, obs, policy=policy, rng=rng)
    else:
        def fn(e, obs):
            _, _, actions, _ = algo.select_actions(e, obs, greedy=True)
            return dict(zip(e.agents, [int(a) for a in actions]))
    return run_episode(env, fn, policy=variant, scenario=scenario_label,
                       scenario_seed=seed, train_seed=train_seed).to_dict()


def main(argv=None):
    parser = argparse.ArgumentParser(description='UbiSched Stage6 Transformer vs MLP benchmark')
    parser.add_argument('--train-episodes', type=int, default=120)
    parser.add_argument('--train-seeds', type=str, default='11')
    parser.add_argument('--eval-scenarios', type=int, default=12)
    parser.add_argument('--batch-size', type=int, default=4)
    parser.add_argument('--ppo-epochs', type=int, default=3)
    parser.add_argument('--hidden', type=int, default=64)
    parser.add_argument('--heads', type=int, default=4)
    parser.add_argument('--layers', type=int, default=2)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'outputs/stage6')
    args = parser.parse_args(argv)
    if min(args.train_episodes, args.eval_scenarios, args.batch_size,
           args.ppo_epochs, args.hidden, args.heads, args.layers) <= 0:
        parser.error('All positive number options must be > 0')
    if args.hidden % args.heads:
        parser.error('--hidden must be divisible by --heads')
    seeds = [int(s.strip()) for s in args.train_seeds.split(',') if s.strip()]
    if not seeds or len(set(seeds)) != len(seeds):
        parser.error('--train-seeds must be unique')
    import torch
    torch.set_num_threads(1)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    evaluation = []
    training = []
    completed = []
    config = {
        'train_seeds': seeds, 'train_episodes': args.train_episodes,
        'eval_cases_per_scenario_and_uav_count': args.eval_scenarios,
        'batch_size': args.batch_size, 'ppo_epochs': args.ppo_epochs,
        'hidden': args.hidden, 'heads': args.heads, 'layers': args.layers,
        'variants': ('mappo_mlp', 'mappo_transformer'),
        'train_uav_count': 3, 'eval_uav_counts': (3, 2),
        'training_scenarios': SUPPORTED_SCENARIOS,
        'evaluation_seed_start': 500000,
        'note': 'Fixed capacities; task count changes within 8 slots. Two-UAV evaluations are held-out configuration, not additional training. Independent model seed repetitions needed.'
    }
    (args.output_dir / 'experiment_config.json').write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')

    def persist(complete=False):
        write_csv(args.output_dir / 'training_log.csv', training)
        write_csv(args.output_dir / 'evaluation_records.csv', evaluation)
        write_csv(args.output_dir / 'comparison_summary.csv', summarize(evaluation))
        (args.output_dir / 'experiment_progress.json').write_text(
            json.dumps({'complete': complete, 'completed_models': completed,
                        'expected_models': len(seeds) * 2}, indent=2, ensure_ascii=False),
            encoding='utf-8')

    eval_config = [
        (scen, cnt, 500000 + si * 10000 + (3-cnt) * 100000 + ci)
        for cnt in (3, 2)
        for si, scen in enumerate(SUPPORTED_SCENARIOS)
        for ci in range(args.eval_scenarios)
    ]
    for scenario, count, seed in eval_config:
        for policy in POLICIES:
            evaluation.append(eval_once(policy=policy, variant=policy, seed=seed,
                                        actual_scenario=scenario, num_uavs=count))
    persist()

    for train_seed in seeds:
        rng = random.Random(train_seed)
        schedule = [(rng.randrange(0, 400000), rng.choice(SUPPORTED_SCENARIOS))
                    for _ in range(args.train_episodes)]
        for name, actor_type in (('mappo_mlp', 'mlp'), ('mappo_transformer', 'transformer')):
            random.seed(train_seed)
            torch.manual_seed(train_seed)
            ref_env = make_env(train_seed, deadline_features=True)
            common = dict(hidden=args.hidden, coordinate_actions=True, work_conserving=True)
            if actor_type == 'mlp':
                algo = MAPPOBaseline(ref_env, **common)
            else:
                algo = TransformerMAPPO(ref_env, heads=args.heads, layers=args.layers, **common)
            for offset in range(0, len(schedule), args.batch_size):
                batch = schedule[offset:offset+args.batch_size]
                episodes = [algo.sample_episode(make_env(s, scenario=t, deadline_features=True))
                            for s, t in batch]
                metrics = algo.update(episodes, epochs=args.ppo_epochs)
                training.append({
                    'policy': name, 'train_seed': train_seed,
                    'episodes': offset+len(batch),
                    'reward_mean': statistics.mean(e.team_reward for e in episodes),
                    'completion_rate_mean': statistics.mean(e.completion_rate for e in episodes),
                    'conflicts_mean': statistics.mean(e.conflicts for e in episodes),
                    **metrics,
                })
            torch.save({
                'actor': algo.actor.state_dict(), 'critic': algo.critic.state_dict(),
                'actor_type': actor_type, 'train_seed': train_seed,
                'episodes': args.train_episodes, 'coordinate_actions': True,
                'work_conserving': True, 'deadline_features': True,
                'architecture': getattr(algo, 'architecture', {'hidden': args.hidden}),
            }, args.output_dir / f'{name}_seed_{train_seed}.pt')
            algo.actor.eval()
            for scenario, count, seed in eval_config:
                evaluation.append(eval_once(
                    policy=name, variant=name, seed=seed,
                    actual_scenario=scenario, num_uavs=count,
                    algo=algo, train_seed=train_seed,
                ))
            completed.append({'policy': name, 'seed': train_seed})
            persist()
            print(f'Saved {name} seed {train_seed}, {args.train_episodes} episodes.', flush=True)
    persist(complete=True)
    print('scenario / policy / completion / deadline_met')
    for item in summarize(evaluation):
        if item['scenario'] == 'urgent':
            print(f"{item['scenario']:12} {item['policy']:22} "
                  f"{item['completion_rate_mean']:.1%} "
                  f"{item['deadline_met_rate_mean']:.1%}")
    print('CSV:', args.output_dir.resolve())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
