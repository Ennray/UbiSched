"""第五阶段：同场景诊断/消融，未涉及 Transformer。

比较基础 MLP-MAPPO、联合动作协调、协调+截止时间特征、再加防空转约束。
四种配置使用相同训练场景序列、相同随机种子和实验指标。
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
from ubisched.experiments.scenarios import SUPPORTED_SCENARIOS, make_env
from ubisched.experiments.evaluation import (
    POLICIES, run_rule_episode, run_mappo_episode
)

VARIANTS = {
    "mappo_original": (False, False, False),
    "mappo_coordinated": (True, False, False),
    "mappo_coordinated_urgency": (True, True, False),
    "mappo_urgency_workconserving": (True, True, True),
}


def write_csv(path: Path, rows: list[dict]):
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _summarize(rows: list[dict]):
    groups = {}
    for row in rows:
        key = (row["policy"], row["scenario"], row["train_seed"])
        groups.setdefault(key, []).append(row)
    output = []
    for (policy, scenario, seed), records in sorted(groups.items(), key=lambda x: (x[0][1], x[0][0], str(x[0][2]))):
        summary = {"policy": policy, "scenario": scenario,
                   "train_seed": "" if seed is None else seed, "samples": len(records)}
        for metric in ("reward", "completion_rate", "deadline_met_rate", "total_energy",
                       "conflicts", "avoidable_wait_steps", "attempted_conflicts", "decisions"):
            values = [float(r[metric]) for r in records]
            summary[metric + "_mean"] = statistics.mean(values)
            summary[metric + "_std"] = statistics.stdev(values) if len(values) > 1 else 0.0
        output.append(summary)
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description="UbiSched Stage5 coordination and urgency ablations")
    parser.add_argument("--train-episodes", type=int, default=120)
    parser.add_argument("--eval-scenarios", type=int, default=12)
    parser.add_argument("--train-seeds", type=str, default="11")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--ppo-epochs", type=int, default=3)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/stage5")
    args = parser.parse_args(argv)
    seeds = [int(v.strip()) for v in args.train_seeds.split(",") if v.strip()]
    if any(v <= 0 for v in (args.train_episodes, args.eval_scenarios, args.batch_size, args.ppo_epochs)):
        parser.error("All experiment counts must be positive")
    if len(seeds) != len(set(seeds)) or not seeds:
        parser.error("Train seeds must be unique non-empty integers")
    import torch
    torch.set_num_threads(1)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cfg = {
        "variants": VARIANTS, "train_seeds": seeds,
        "train_episodes": args.train_episodes,
        "eval_scenarios_per_type": args.eval_scenarios,
        "batch_size": args.batch_size, "ppo_epochs": args.ppo_epochs,
        "evaluation_seed_start": 500000,
        "note": "Same simulator and external seeds. Model improvements are exploratory, not Transformer results.",
    }
    (args.output_dir / "experiment_config.json").write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

    records = []
    training = []
    completed_models = []

    def save_progress(complete=False):
        # 长实验逐模型持久化；如果被中断，进度文件明确标识为未完成。
        write_csv(args.output_dir / "evaluation_records.csv", records)
        write_csv(args.output_dir / "comparison_summary.csv", _summarize(records))
        write_csv(args.output_dir / "training_log.csv", training)
        (args.output_dir / "experiment_progress.json").write_text(
            json.dumps({"complete": complete, "completed_models": completed_models,
                        "requested_models": len(seeds) * len(VARIANTS)},
                       indent=2, ensure_ascii=False), encoding="utf-8")
    for scenario_index, scenario in enumerate(SUPPORTED_SCENARIOS):
        for case_i in range(args.eval_scenarios):
            test_seed = 500000 + scenario_index * 10000 + case_i
            for policy in POLICIES:
                records.append(run_rule_episode(scenario_seed=test_seed, scenario=scenario,
                                                policy=policy).to_dict())

    save_progress()
    for train_seed in seeds:
        rng = random.Random(train_seed)
        schedule = [
            (rng.randrange(0, 400000), rng.choice(SUPPORTED_SCENARIOS))
            for _ in range(args.train_episodes)
        ]
        for name, (coordinate, urgency, work_conserving) in VARIANTS.items():
            random.seed(train_seed)
            torch.manual_seed(train_seed)
            algo = MAPPOBaseline(
                make_env(train_seed, deadline_features=urgency),
                coordinate_actions=coordinate, work_conserving=work_conserving,
            )
            for offset in range(0, len(schedule), args.batch_size):
                current = schedule[offset:offset + args.batch_size]
                episodes = [algo.sample_episode(make_env(s, scenario=t, deadline_features=urgency))
                            for s, t in current]
                stats = algo.update(episodes, epochs=args.ppo_epochs)
                training.append({"policy": name, "train_seed": train_seed,
                                 "episodes": offset + len(current),
                                 "reward_mean": statistics.mean(ep.team_reward for ep in episodes),
                                 "completion_rate_mean": statistics.mean(ep.completion_rate for ep in episodes),
                                 "conflicts_mean": statistics.mean(ep.conflicts for ep in episodes),
                                 **stats})
            torch.save({"actor": algo.actor.state_dict(), "critic": algo.critic.state_dict(),
                        "coordinate_actions": coordinate, "deadline_features": urgency,
                        "work_conserving": work_conserving,
                        "train_seed": train_seed, "episodes": args.train_episodes},
                       args.output_dir / f"{name}_seed_{train_seed}.pt")
            for scenario_index, scenario in enumerate(SUPPORTED_SCENARIOS):
                for case_i in range(args.eval_scenarios):
                    test_seed = 500000 + scenario_index * 10000 + case_i
                    result = run_mappo_episode(
                        algo, scenario_seed=test_seed, scenario=scenario,
                        train_seed=train_seed, policy_name=name,
                    )
                    records.append(result.to_dict())
            completed_models.append({"variant": name, "seed": train_seed})
            save_progress()
            print(f"已训练 {name}, seed={train_seed}, episodes={args.train_episodes}", flush=True)

    save_progress(complete=True)
    print("场景 / 策略 / 完成率 / 冲突次数 / 可避免等待步数")
    for item in _summarize(records):
        print(f"  {item['scenario']:10s} {item['policy']:27s} "
              f"{item['completion_rate_mean']:.1%} "
              f"{item['conflicts_mean']:.2f} {item['avoidable_wait_steps_mean']:.2f}")
    print(f"结果目录：{args.output_dir.resolve()}")
    print("说明：以上是小规模探索实验，不保证任何一种学习策略优于 EDF。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
