"""第八阶段：软截止时间下，原依赖Transformer与关键路径增强Transformer对比。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ubisched.algorithms.transformer_mappo import (
    DependencyAwareTransformerMAPPO, CriticalPathTransformerMAPPO,
)
from ubisched.experiments.evaluation import POLICIES, choose_rule_actions, run_episode
from ubisched.experiments.scenarios import STAGE7_SCENARIOS, make_env
from ubisched.scheduling.scheduler_env import RewardConfig
from run_stage6_transformer import write_csv

MODELS = {"dependency_transformer_v7_soft": DependencyAwareTransformerMAPPO,
          "critical_transformer_v8": CriticalPathTransformerMAPPO}


def reward_config():
    # 所有算法使用相同的软截止时间环境与奖励；不是沿用旧的硬截止时间得分。
    return RewardConfig(late_fixed_penalty=0.3, late_time_penalty=0.05)


def env_factory(seed, scenario="normal", num_uavs=3):
    return make_env(seed, scenario=scenario, num_uavs=num_uavs,
                    deadline_features=True, dependency_features=True,
                    critical_path_features=True, soft_deadlines=True,
                    reward_config=reward_config())


def evaluate(policy, scenario, seed, n_uavs, algo=None, train_seed=None):
    env = env_factory(seed, scenario, n_uavs)
    if algo is None:
        rng = random.Random(seed + 3917)
        decision = lambda e, o: choose_rule_actions(e, o, policy=policy, rng=rng)
    else:
        def decision(e, o):
            _, _, acts, _ = algo.select_actions(e, o, greedy=True)
            return {a: int(acts[i]) for i, a in enumerate(e.agents)}
    label = scenario if n_uavs == 3 else f"{scenario}_2uav"
    return run_episode(env, decision, policy=policy, scenario=label,
                       scenario_seed=seed, train_seed=train_seed).to_dict()


def summarize(rows):
    grouped = {}
    for row in rows:
        key = (row['policy'], row['scenario'], row['train_seed'])
        grouped.setdefault(key, []).append(row)
    summary = []
    for (policy, scenario, seed), group in sorted(grouped.items(), key=str):
        entry = {'policy': policy, 'scenario': scenario, 'train_seed': seed,
                 'samples': len(group)}
        for key in ('completion_rate', 'deadline_met_rate', 'late_finished_tasks',
                    'total_lateness', 'reward', 'total_energy', 'conflicts'):
            values = [float(x[key]) for x in group]
            entry[key + '_mean'] = statistics.mean(values)
            entry[key + '_std'] = statistics.stdev(values) if len(values) > 1 else 0.0
        summary.append(entry)
    return summary


def cross_seed_summary(records):
    """先对每个训练种子求均值，再跨种子聚合；避免把重复测试场景当独立训练。"""
    groups = {}
    for entry in summarize(records):
        groups.setdefault((entry['policy'], entry['scenario']), []).append(entry)
    output = []
    for (policy, scenario), rows in sorted(groups.items()):
        result = {'policy': policy, 'scenario': scenario,
                  'training_seeds': len(rows),
                  'cases_per_training_seed': rows[0]['samples']}
        for key in ('deadline_met_rate', 'completion_rate', 'late_finished_tasks',
                    'total_lateness', 'reward', 'total_energy'):
            vals = [float(x[key + '_mean']) for x in rows]
            result[key + '_mean'] = statistics.mean(vals)
            result[key + '_std_across_train_seeds'] = (statistics.stdev(vals)
                                                       if len(vals) > 1 else 0.0)
        output.append(result)
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description="Critical-path Transformer-MAPPO benchmarking")
    parser.add_argument('--train-episodes', type=int, default=120)
    parser.add_argument('--train-seeds', default='11,29,47')
    parser.add_argument('--eval-scenarios', type=int, default=12)
    parser.add_argument('--batch-size', type=int, default=4)
    parser.add_argument('--ppo-epochs', type=int, default=3)
    parser.add_argument('--hidden', type=int, default=32)
    parser.add_argument('--heads', type=int, default=4)
    parser.add_argument('--layers', type=int, default=1)
    parser.add_argument('--output-dir', type=Path, default=ROOT/'outputs/stage8')
    args = parser.parse_args(argv)
    if min(args.train_episodes,args.eval_scenarios,args.batch_size,args.ppo_epochs,
           args.hidden,args.heads,args.layers) <= 0 or args.hidden % args.heads:
        parser.error('Numeric values must be positive and hidden must be divisible by heads')
    seeds = [int(x.strip()) for x in args.train_seeds.split(',') if x.strip()]
    if not seeds or len(seeds) != len(set(seeds)):
        parser.error('Train seeds must be distinct')
    import torch
    torch.set_num_threads(1)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cases = [(scene, uavs, 810000 + i * 10000 + (3-uavs)*100000 + j)
             for uavs in (3, 2)
             for i, scene in enumerate(STAGE7_SCENARIOS)
             for j in range(args.eval_scenarios)]
    config = {'training_scenarios': STAGE7_SCENARIOS,
              'train_seeds': seeds, 'train_episodes_per_seed': args.train_episodes,
              'test_scenarios_per_type_and_uav_count': args.eval_scenarios,
              'train_uav_count': 3, 'eval_uav_counts': [3,2],
              'batch_size':args.batch_size,'ppo_epochs':args.ppo_epochs,
              'hidden':args.hidden,'heads':args.heads,'layers':args.layers,
              'strategies': [*POLICIES, *MODELS],
              'strict_deadlines': False, 'late_fixed_penalty': 0.3,
              'late_time_penalty':0.05,
              'note': 'New soft-deadline simulation: do not compare numerically with stages 4-7 hard-deadline results. Optimistic critical path is a feature estimate, not an execution schedule.'}
    (args.output_dir/'experiment_config.json').write_text(
        json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    records=[]
    logs=[]
    completed=[]
    def save(complete=False):
        write_csv(args.output_dir/'evaluation_records.csv',records)
        write_csv(args.output_dir/'comparison_summary.csv',summarize(records))
        write_csv(args.output_dir/'cross_seed_summary.csv',cross_seed_summary(records))
        write_csv(args.output_dir/'training_log.csv',logs)
        (args.output_dir/'progress.json').write_text(json.dumps({
            'complete':complete,'completed_models':completed,
            'expected_models':len(seeds)*len(MODELS)
        },ensure_ascii=False,indent=2),encoding='utf-8')
    for scene,n_uavs,case_seed in cases:
        for rule in POLICIES:
            records.append(evaluate(rule,scene,case_seed,n_uavs))
    save()
    for seed in seeds:
        schedule_rng = random.Random(seed)
        schedule = [(schedule_rng.randrange(0,500000),schedule_rng.choice(STAGE7_SCENARIOS))
                    for _ in range(args.train_episodes)]
        for name,model in MODELS.items():
            random.seed(seed)
            torch.manual_seed(seed)
            agent = model(env_factory(seed), hidden=args.hidden,heads=args.heads,
                          layers=args.layers,coordinate_actions=True,work_conserving=True)
            for offset in range(0,len(schedule),args.batch_size):
                batch = [agent.sample_episode(env_factory(s,scene)) for s,scene in schedule[offset:offset+args.batch_size]]
                stats = agent.update(batch,epochs=args.ppo_epochs)
                logs.append({'policy':name,'train_seed':seed,
                             'episodes':offset+len(batch),
                             'reward_mean':statistics.mean(x.team_reward for x in batch),
                             'completion_mean':statistics.mean(x.completion_rate for x in batch),
                             **stats})
            torch.save({'actor':agent.actor.state_dict(),'critic':agent.critic.state_dict(),
                        'architecture':agent.architecture,'actor_type':agent.actor_kind,
                        'soft_deadlines':True,'late_fixed_penalty':0.3,
                        'late_time_penalty':0.05,'seed':seed,'episodes':args.train_episodes},
                       args.output_dir/f'{name}_seed_{seed}.pt')
            agent.actor.eval()
            for scene,n_uavs,case_seed in cases:
                records.append(evaluate(name,scene,case_seed,n_uavs,
                                        algo=agent,train_seed=seed))
            completed.append({'policy':name,'seed':seed})
            save()
            print(f'已完成 {name}, seed={seed}, {args.train_episodes}局',flush=True)
    save(complete=True)
    for x in summarize(records):
        if x['scenario'] in ('urgent','dependency'):
            print(x['policy'],x['scenario'],
                  f"完成率={x['completion_rate_mean']:.1%}",
                  f"按时率={x['deadline_met_rate_mean']:.1%}",
                  f"超期总时长={x['total_lateness_mean']:.2f}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
