"""第四阶段：可重复训练与规则调度横向对比。

默认训练量是方便本地验证的规模，不是论文正式实验要求。
正式结果应增加训练回合、独立随机种子和测试场景，并报告方差。
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
from ubisched.experiments.evaluation import POLICIES, run_mappo_episode, run_rule_episode
from ubisched.experiments.scenarios import SUPPORTED_SCENARIOS, make_env


def _parse_seeds(value: str) -> list[int]:
    result = [int(x.strip()) for x in value.split(",") if x.strip()]
    if not result or len(result) != len(set(result)):
        raise argparse.ArgumentTypeError("Provide unique comma-separated integer seeds")
    return result


def train_seed_model(train_seed: int, episodes: int, *, batch_size: int,
                     ppo_epochs: int, lr: float, output_dir: Path):
    import torch
    rng = random.Random(train_seed)
    random.seed(train_seed)
    torch.manual_seed(train_seed)
    scenarios = list(SUPPORTED_SCENARIOS)
    algo = MAPPOBaseline(make_env(train_seed), lr=lr)
    reports = []
    for start in range(0, episodes, batch_size):
        batch = []
        for _ in range(min(batch_size, episodes - start)):
            scenario_seed = rng.randrange(0, 400_000)
            scenario = rng.choice(scenarios)
            batch.append(algo.sample_episode(make_env(scenario_seed, scenario=scenario)))
        metrics = algo.update(batch, epochs=ppo_epochs)
        reports.append({
            "train_seed": train_seed,
            "episodes": start + len(batch),
            "training_reward": statistics.mean(x.team_reward for x in batch),
            "training_completion": statistics.mean(x.completion_rate for x in batch),
            "training_conflicts": statistics.mean(x.conflicts for x in batch),
            **metrics,
        })
    torch.save({
        "actor": algo.actor.state_dict(), "critic": algo.critic.state_dict(),
        "agent_ids": algo.agent_ids, "action_dim": algo.action_dim,
        "train_seed": train_seed, "episodes": episodes,
        "note": "Stage4 MLP-MAPPO, 3 UAVs, 1 resource per UAV, max_tasks=8",
    }, output_dir / f"mappo_mlp_seed_{train_seed}.pt")
    return algo, reports


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8-sig") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows: list[dict]) -> list[dict]:
    groups = {}
    for row in rows:
        key = (row["policy"], row["scenario"], row["train_seed"])
        groups.setdefault(key, []).append(row)
    out = []
    for (policy, scenario, train_seed), items in sorted(
        groups.items(), key=lambda x: (x[0][1], x[0][0], str(x[0][2]))
    ):
        entry = {"policy": policy, "scenario": scenario,
                 "train_seed": "" if train_seed is None else train_seed,
                 "samples": len(items)}
        for metric in ("reward", "completion_rate", "deadline_met_rate",
                       "makespan", "total_energy", "energy_per_finished", "quality_mean_finished", "conflicts", "decisions", "avoidable_wait_steps", "attempted_conflicts"):
            values = [float(x[metric]) for x in items if x[metric] is not None]
            entry[f"{metric}_mean"] = statistics.mean(values) if values else ""
            entry[f"{metric}_std"] = statistics.stdev(values) if len(values) > 1 else 0.0 if values else ""
        entry["completed_episodes"] = sum(x["status"] == "completed" for x in items)
        out.append(entry)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description="UbiSched Stage 4 fair scenario benchmark")
    parser.add_argument("--train-episodes", type=int, default=80)
    parser.add_argument("--train-seeds", type=_parse_seeds, default=[11, 29])
    parser.add_argument("--eval-scenarios", type=int, default=12,
                        help="每类场景独立测试次数；全部算法复用相同测试种子")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--ppo-epochs", type=int, default=3)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/stage4")
    args = parser.parse_args(argv)
    if args.train_episodes < 1 or args.eval_scenarios < 1 or args.batch_size < 1 or args.ppo_epochs < 1:
        parser.error("Training and evaluation counts must be positive")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    import torch
    torch.set_num_threads(1)
    configs = {"train_episodes": args.train_episodes, "train_seeds": args.train_seeds,
               "eval_scenarios_per_type": args.eval_scenarios, "batch_size": args.batch_size,
               "ppo_epochs": args.ppo_epochs, "lr": args.lr,
               "scenarios": SUPPORTED_SCENARIOS,
               "eval_seed_start": 500_000,
               "algorithm": "stage3 MLP-MAPPO, deterministic argmax evaluation"}
    (args.output_dir / "experiment_config.json").write_text(
        json.dumps(configs, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[1/3] 同场景规则/随机基线（不用训练）")
    rows = []
    for variant_i, variant in enumerate(SUPPORTED_SCENARIOS):
        for i in range(args.eval_scenarios):
            case_seed = 500_000 + variant_i * 10_000 + i
            for policy in POLICIES:
                result = run_rule_episode(scenario_seed=case_seed, scenario=variant, policy=policy)
                rows.append(result.to_dict())

    print("[2/3] 独立训练多个 MAPPO 模型，并在完全相同的测试场景评估")
    training_rows = []
    for train_seed in args.train_seeds:
        algo, log = train_seed_model(train_seed, args.train_episodes,
                                      batch_size=args.batch_size, ppo_epochs=args.ppo_epochs,
                                      lr=args.lr, output_dir=args.output_dir)
        training_rows.extend(log)
        for variant_i, variant in enumerate(SUPPORTED_SCENARIOS):
            for i in range(args.eval_scenarios):
                case_seed = 500_000 + variant_i * 10_000 + i
                result = run_mappo_episode(algo, scenario_seed=case_seed,
                                           scenario=variant, train_seed=train_seed)
                rows.append(result.to_dict())
        print(f"  已完成 seed={train_seed}，训练 {args.train_episodes} 局")
    print("[3/3] 输出复现实验材料")
    _write_csv(args.output_dir / "evaluation_records.csv", rows)
    _write_csv(args.output_dir / "comparison_summary.csv", summarize(rows))
    _write_csv(args.output_dir / "training_log.csv", training_rows)
    print(f"全部结果：{args.output_dir.resolve()}")
    print("各场景平均完成率（%%）与奖励（均值），详细标准差见 comparison_summary.csv")
    for row in summarize(rows):
        print(f"  {row['scenario']:10s} {row['policy']:17s} seed={str(row['train_seed']):>3s} "
              f"完成率={row['completion_rate_mean']:.1%} 奖励={row['reward_mean']:+.3f} "
              f"超时/未完={1-row['deadline_met_rate_mean']:.1%}")
    print("注意：运行成功不代表 MAPPO 超越基线；小规模示例不能直接用于论文结论。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
