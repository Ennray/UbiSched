"""第十一阶段：完整感算协同仿真环境内，规则与 MAPPO 的同场景对比。

仅使用合成场景，不冒充实测；训练/测试种子独立；记录跨机、排队与超期。
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
from ubisched.algorithms.transformer_mappo import DependencyAwareTransformerMAPPO
from ubisched.experiments.evaluation import POLICIES, choose_rule_actions, run_episode
from ubisched.experiments.integrated_scenario import NETWORK_CONDITIONS, make_integrated_env

MODELS = {"mappo_mlp": MAPPOBaseline,
          "mappo_dependency_transformer": DependencyAwareTransformerMAPPO}
MEASURES = ("completion_rate", "deadline_met_rate", "reward", "makespan",
            "total_energy", "conflicts", "remote_computes", "local_computes",
            "communication_queue_wait", "transmission_count", "total_lateness")


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def evaluate(policy: str, case_seed: int, condition: str, *, algo=None, train_seed=None):
    env = make_integrated_env(case_seed, condition=condition)
    rng = random.Random(case_seed + 101)
    if algo is None:
        fn = lambda e, obs: choose_rule_actions(e, obs, policy=policy, rng=rng)
    else:
        def fn(e, obs):
            _, _, actions, _ = algo.select_actions(e, obs, greedy=True)
            return {agent: int(actions[i]) for i, agent in enumerate(e.agents)}
    if algo is not None:
        was_training = algo.actor.training
        algo.actor.eval()
    try:
        row = run_episode(env, fn, policy=policy, scenario=condition,
                          scenario_seed=case_seed, train_seed=train_seed).to_dict()
    finally:
        if algo is not None:
            algo.actor.train(was_training)
    assignments = [x for x in env.state.assignments if x.status == 'finished']
    classify = [x for x in assignments if x.subtask_id.startswith('infer_')]
    row.update({
        "remote_computes": sum(env.state.get_resource(a.resource_id).owner_uav_id != 'UAV1'
                               for a in classify),
        "local_computes": sum(env.state.get_resource(a.resource_id).owner_uav_id == 'UAV1'
                              for a in classify),
        "communication_queue_wait": sum(a.communication_queue_wait for a in assignments),
        "transmission_count": sum(1 for hop in env.state.transfer_reservations
                                  if hop.status == 'finished'),
    })
    return row


def summary(rows: list[dict]):
    groups = {}
    for row in rows:
        groups.setdefault((row['policy'], row['scenario'], row['train_seed']), []).append(row)
    result=[]
    for (policy, scenario, seed), group in sorted(groups.items(), key=str):
        item={"policy":policy,"scenario":scenario,"train_seed":seed,"samples":len(group)}
        for key in MEASURES:
            vals=[float(r[key]) for r in group]
            item[key+'_mean']=statistics.mean(vals)
            item[key+'_std']=statistics.stdev(vals) if len(vals)>1 else 0.0
        result.append(item)
    return result


def cross_seed_summary(records):
    groups={}
    for r in summary(records):
        groups.setdefault((r['policy'], r['scenario']),[]).append(r)
    out=[]
    for (policy, scenario), rows in sorted(groups.items()):
        item={"policy":policy,"scenario":scenario,
              "train_seeds":len(rows),"test_cases_per_seed":rows[0]['samples']}
        for key in MEASURES:
            vals=[row[key+'_mean'] for row in rows]
            item[key+'_mean']=statistics.mean(vals)
            item[key+'_std_across_seeds']=(statistics.stdev(vals) if len(vals)>1 else 0.0)
        out.append(item)
    return out


def main(argv=None):
    parser=argparse.ArgumentParser(description='UbiSched 感算协同端到端仿真基准')
    parser.add_argument('--train-episodes',type=int,default=60)
    parser.add_argument('--train-seeds',default='11,29,47')
    parser.add_argument('--eval-cases',type=int,default=12)
    parser.add_argument('--batch-size',type=int,default=4)
    parser.add_argument('--ppo-epochs',type=int,default=2)
    parser.add_argument('--hidden',type=int,default=32)
    parser.add_argument('--heads',type=int,default=4)
    parser.add_argument('--layers',type=int,default=1)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'outputs/stage11')
    args=parser.parse_args(argv)
    nums=(args.train_episodes,args.eval_cases,args.batch_size,args.ppo_epochs,
          args.hidden,args.heads,args.layers)
    if min(nums)<=0 or args.hidden%args.heads:
        parser.error('数值参数必须大于0，hidden 必须可以整除 heads')
    seeds=[int(part.strip()) for part in args.train_seeds.split(',') if part.strip()]
    if not seeds or len(seeds)!=len(set(seeds)):
        parser.error('必须提供不重复的训练随机种子')
    import torch
    torch.set_num_threads(1)
    args.output_dir.mkdir(parents=True,exist_ok=True)
    cases=[(condition, 910000+i) for condition in NETWORK_CONDITIONS
           for i in range(args.eval_cases)]
    config={"train_seeds":seeds,"train_episodes":args.train_episodes,
            "train_conditions":NETWORK_CONDITIONS,
            "eval_conditions":NETWORK_CONDITIONS,
            "test_seeds":[910000+i for i in range(args.eval_cases)],
            "model_names":list(MODELS),"rule_names":list(POLICIES),
            "batch_size":args.batch_size,"ppo_epochs":args.ppo_epochs,
            "hidden":args.hidden,"heads":args.heads,"layers":args.layers,
            "deadline_model":"soft deadlines; late completions recorded",
            "communication_model":"directed exclusive links, simulated reservations",
            "stress_case_note":"contended case disables local and backup CPU, isolates single-link contention",
            "caution":"No real UAV command execution or AirSim measured transmission."}
    (args.output_dir/'experiment_config.json').write_text(
        json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    records=[]; logs=[]; complete=[]
    def save(finished=False):
        write_csv(args.output_dir/'evaluation_records.csv',records)
        write_csv(args.output_dir/'comparison_summary.csv',summary(records))
        write_csv(args.output_dir/'cross_seed_summary.csv',cross_seed_summary(records))
        write_csv(args.output_dir/'training_log.csv',logs)
        (args.output_dir/'progress.json').write_text(
            json.dumps({"finished":finished,"completed_model_runs":complete,
                        "expected_model_runs":len(seeds)*len(MODELS)},ensure_ascii=False,indent=2),
            encoding='utf-8')
    for condition,s in cases:
        for policy in POLICIES:
            records.append(evaluate(policy,s,condition))
    save()
    for train_seed in seeds:
        training_rng=random.Random(train_seed)
        # 两种模型完全共享训练场景顺序；测试集与训练集种子隔离。
        training_cases=[(training_rng.randint(0,200000), training_rng.choice(NETWORK_CONDITIONS))
                        for _ in range(args.train_episodes)]
        for name, model_class in MODELS.items():
            random.seed(train_seed)
            torch.manual_seed(train_seed)
            params={"hidden":args.hidden,"coordinate_actions":True,"work_conserving":True}
            if model_class is DependencyAwareTransformerMAPPO:
                params.update(heads=args.heads,layers=args.layers)
            algo=model_class(make_integrated_env(train_seed),**params)
            for offset in range(0,len(training_cases),args.batch_size):
                batch=[algo.sample_episode(make_integrated_env(s,condition=c))
                       for s,c in training_cases[offset:offset+args.batch_size]]
                stats=algo.update(batch,epochs=args.ppo_epochs)
                logs.append({"model":name,"train_seed":train_seed,
                             "trained_episodes":offset+len(batch),
                             "reward_mean":statistics.mean(ep.team_reward for ep in batch),
                             "completion_mean":statistics.mean(ep.completion_rate for ep in batch),
                             **stats})
            # 仅保存模型参数和结构配置，不执行来自外部的对象反序列化。
            torch.save({"actor":algo.actor.state_dict(),"critic":algo.critic.state_dict(),
                        "model":name,"train_seed":train_seed,
                        "training_episodes":args.train_episodes,
                        "hidden":args.hidden,"heads":args.heads,"layers":args.layers},
                       args.output_dir/f'{name}_seed_{train_seed}.pt')
            for condition,s in cases:
                records.append(evaluate(name,s,condition,algo=algo,train_seed=train_seed))
            complete.append({"model":name,"seed":train_seed})
            save()
            print(f"训练及评估完成：{name}，seed={train_seed}",flush=True)
    save(finished=True)
    print('各策略概览（按种子汇总）')
    for row in cross_seed_summary(records):
        print(row['policy'],row['scenario'],f"完成率={row['completion_rate_mean']:.1%}",
              f"按时率={row['deadline_met_rate_mean']:.1%}",
              f"通信排队={row['communication_queue_wait_mean']:.2f}s")
    return 0


if __name__=='__main__':
    raise SystemExit(main())
