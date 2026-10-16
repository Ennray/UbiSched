"""第三阶段演示：3架 UAV 共同决策、相同任务冲突与任务依赖。"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ubisched.graph.match_matrix import RuleBasedScorer
from ubisched.graph.resource_graph import ResourceGraph
from ubisched.graph.task_graph import TaskGraph
from ubisched.scheduling.multi_agent_env import MultiAgentSchedulerEnv


def make_env() -> MultiAgentSchedulerEnv:
    resources = ResourceGraph.from_yaml(ROOT / "configs/ubisched/resource_graph_example.yaml")
    backup = deepcopy(resources.resources[0])
    backup.resource_id = "uav_3_rgb_sensor"
    backup.owner_uav_id = "uav_3"
    resources.resources.append(backup)
    return MultiAgentSchedulerEnv(
        TaskGraph.from_yaml(ROOT / "configs/ubisched/task_graph_example.yaml"),
        resources,
        RuleBasedScorer.from_yaml(ROOT / "configs/ubisched/match_scoring.yaml"),
        max_tasks=4, max_resources_per_uav=2, max_agents=3,
    )


def main():
    env = make_env()
    observations, info = env.reset()
    total_reward = 0.0
    for round_id in range(20):
        actions = {agent: env.noop_index for agent in env.agents}
        # 第一轮让 UAV1、UAV3 故意争夺同一任务，展示联合冲突处理。
        if round_id == 0:
            actions["uav_1"] = observations["uav_1"]["action_labels"].index(
                ("detect_target", "uav_1_rgb_sensor")
            )
            actions["uav_3"] = observations["uav_3"]["action_labels"].index(
                ("detect_target", "uav_3_rgb_sensor")
            )
        else:
            for agent in env.agents:
                mask = observations[agent]["action_mask"]
                available = [i for i in range(env.noop_index) if mask[i]]
                if available:
                    actions[agent] = available[0]
        observations, reward, ended, truncated, info = env.step(actions)
        total_reward += reward
        print(
            f"轮次 {round_id+1:2d}  t={info['time']:5.2f}s  "
            f"分配={info['started']}  完成={info['completed']}  "
            f"冲突={info['conflicts_this_step']}  奖励={reward:+.3f}"
        )
        if ended or truncated:
            break
    print(f"状态={info['status']}，完成率={info['completion_rate']:.0%}，累计团队奖励={total_reward:+.3f}")


if __name__ == "__main__":
    main()
