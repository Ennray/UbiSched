"""运行教学版基础 MAPPO。仅验证训练流程，不表示科研性能已经验证。"""
from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ubisched.graph.match_matrix import RuleBasedScorer
from ubisched.graph.resource_graph import ResourceGraph
from ubisched.graph.task_graph import TaskGraph, TaskEdge
from ubisched.algorithms.mappo_baseline import MAPPOBaseline
from ubisched.scheduling.multi_agent_env import MultiAgentSchedulerEnv


def make_env() -> MultiAgentSchedulerEnv:
    tasks = TaskGraph.from_yaml(ROOT / "configs/ubisched/task_graph_example.yaml")
    resources = ResourceGraph.from_yaml(ROOT / "configs/ubisched/resource_graph_example.yaml")
    backup = deepcopy(resources.resources[0])
    backup.resource_id = "uav_3_rgb_sensor"
    backup.owner_uav_id = "uav_3"
    backup.power = 24.0
    backup.sensing_quality = {"rgb": 0.79, "infrared": 0.76}
    resources.resources.append(backup)
    # 新增独立检测任务及其后续计算任务，使两个传感器可以真正并行。
    detect2 = deepcopy(tasks.subtasks[0])
    detect2.subtask_id = "detect_target_2"
    detect2.location = [102.0, 51.0, 0.0]
    classify2 = deepcopy(tasks.subtasks[1])
    classify2.subtask_id = "classify_target_2"
    tasks.subtasks.extend([detect2, classify2])
    tasks.edges.append(TaskEdge("detect_target_2", "classify_target_2"))
    return MultiAgentSchedulerEnv(
        tasks, resources,
        RuleBasedScorer.from_yaml(ROOT / "configs/ubisched/match_scoring.yaml"),
        max_tasks=4, max_resources_per_uav=1, max_agents=3,
        max_steps=60,
    )


def main():
    parser = argparse.ArgumentParser(description="运行最小 MAPPO 联通训练")
    parser.add_argument("--episodes", type=int, default=40)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--save", type=Path, default=None, help="可选，保存模型权重 .pt")
    args = parser.parse_args()
    import torch
    torch.set_num_threads(1)
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    algo = MAPPOBaseline(make_env())
    print("开始训练：共享MLP Actor + 集中式Critic + 团队奖励 + 动作掩码")
    reports = algo.train(make_env, episodes=args.episodes)
    greedy_results = [algo.sample_episode(make_env(), greedy=True) for _ in range(5)]
    print("贪心评估5次（固定示例配置，并非泛化实验）：")
    print(
        f"  平均完成率 {sum(x.completion_rate for x in greedy_results)/5:.0%}，"
        f"平均奖励 {sum(x.team_reward for x in greedy_results)/5:+.3f}，"
        f"总冲突 {sum(x.conflicts for x in greedy_results)}"
    )
    if args.save is not None:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        torch.save({
            "actor": algo.actor.state_dict(),
            "critic": algo.critic.state_dict(),
            "agent_ids": algo.agent_ids,
            "action_dim": algo.action_dim,
            "episodes": args.episodes,
        }, args.save)
        print(f"已保存训练权重：{args.save}")


if __name__ == "__main__":
    main()
