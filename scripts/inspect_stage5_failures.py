"""复盘阶段5具体失败样本，比较 EDF 与已训练 MAPPO 的启动顺序及未完成任务。"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ubisched.algorithms.mappo_baseline import MAPPOBaseline
from ubisched.experiments.evaluation import choose_rule_actions
from ubisched.experiments.scenarios import SUPPORTED_SCENARIOS, make_env


def trace_one(env, action_fn):
    obs, _ = env.reset()
    trace = []
    while True:
        current = env.state.now
        chosen = action_fn(env, obs)
        decisions = []
        for agent in env.agents:
            action = chosen[agent]
            label = obs[agent]["action_labels"][action]
            decisions.append({"agent": agent, "task": label[0] if label else None,
                              "resource": label[1] if label else None})
        obs, reward, terminated, truncated, info = env.step(chosen)
        trace.append({"time": current, "chosen": decisions,
                      "started": info["started"], "completed": info["completed"],
                      "reward": reward, "reason": info["reason"],
                      "conflicts": info["conflicts_this_step"]})
        if terminated or truncated:
            break
    return {
        "completion_rate": info["completion_rate"],
        "deadline_met_rate": info["deadline_met_rate"],
        "unfinished": [{"task": t.subtask_id, "deadline": t.deadline,
                        "state": t.state, "priority": t.priority}
                       for t in env.state.task_graph.subtasks if t.state != "finished"],
        "event_trace": trace,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Stage5 per-case EDF vs MAPPO trace")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--scenario", choices=SUPPORTED_SCENARIOS, default="urgent")
    parser.add_argument("--cases", type=int, default=12)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/stage5_failure_cases")
    args = parser.parse_args(argv)
    if args.cases <= 0:
        parser.error("cases must be positive")
    import torch
    torch.set_num_threads(1)
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    deadline_features = bool(checkpoint["deadline_features"])
    algo = MAPPOBaseline(make_env(1, deadline_features=deadline_features),
                         coordinate_actions=bool(checkpoint["coordinate_actions"]),
                         work_conserving=bool(checkpoint.get("work_conserving", False)))
    algo.actor.load_state_dict(checkpoint["actor"])
    algo.actor.eval()

    variant_offset = SUPPORTED_SCENARIOS.index(args.scenario) * 10000
    summary, failures = [], []
    for index in range(args.cases):
        seed = 500000 + variant_offset + index
        rng = random.Random(seed + 3917)
        edf = trace_one(make_env(seed, scenario=args.scenario),
                        lambda env, obs: choose_rule_actions(env, obs,
                                                             policy="earliest_deadline", rng=rng))
        learned = trace_one(make_env(seed, scenario=args.scenario,
                                     deadline_features=deadline_features),
                            lambda env, obs: dict(zip(env.agents,
                                algo.select_actions(env, obs, greedy=True)[2].tolist())))
        entry = {"scenario_seed": seed,
                 "edf_completion": edf["completion_rate"],
                 "mappo_completion": learned["completion_rate"],
                 "edf_unfinished": ",".join(x["task"] for x in edf["unfinished"]),
                 "mappo_unfinished": ",".join(x["task"] for x in learned["unfinished"])}
        summary.append(entry)
        if learned["completion_rate"] < edf["completion_rate"]:
            failures.append({"scenario_seed": seed, "edf": edf, "mappo": learned})
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "failure_summary.csv").open("w", newline="", encoding="utf-8-sig") as fp:
        writer = csv.DictWriter(fp, fieldnames=summary[0].keys())
        writer.writeheader()
        writer.writerows(summary)
    (args.output_dir / "failure_traces.json").write_text(
        json.dumps(failures, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"对比 {args.cases} 个{args.scenario}场景，MAPPO劣于EDF的样本 {len(failures)} 个")
    for row in summary:
        if row["mappo_completion"] < row["edf_completion"]:
            print("  case", row["scenario_seed"], "EDF", f"{row['edf_completion']:.0%}",
                  "MAPPO", f"{row['mappo_completion']:.0%}",
                  "未完成", row["mappo_unfinished"])
    print("逐步动作和未完成任务见 failure_traces.json；这只描述失败样本，不能单独归因。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
