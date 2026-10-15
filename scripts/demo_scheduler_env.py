"""第二阶段演示：相同的UbiSched环境运行规则策略与随机可行策略。"""
from __future__ import annotations

import random
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ubisched.graph.match_matrix import RuleBasedScorer
from ubisched.graph.resource_graph import ResourceGraph
from ubisched.graph.task_graph import TaskGraph
from ubisched.scheduling.rule_based_scheduler import RuleBasedScheduler
from ubisched.scheduling.scheduler_env import SchedulerEnv


def create_env() -> SchedulerEnv:
    resources = ResourceGraph.from_yaml(ROOT / "configs/ubisched/resource_graph_example.yaml")
    # 添加一台可用但感知质量稍差的备用 UAV，让规则和随机策略有不同选择。
    backup = deepcopy(resources.resources[0])
    backup.resource_id = "uav_3_rgb_sensor"
    backup.owner_uav_id = "uav_3"
    backup.sensing_quality = {"rgb": 0.78, "infrared": 0.76}
    backup.power = 20.0
    resources.resources.append(backup)
    return SchedulerEnv(
        TaskGraph.from_yaml(ROOT / "configs/ubisched/task_graph_example.yaml"),
        resources,
        RuleBasedScorer.from_yaml(ROOT / "configs/ubisched/match_scoring.yaml"),
    )


def pick_rule(env: SchedulerEnv, obs: dict) -> int:
    """复用原有最高匹配分数策略，返回环境动作索引。"""
    matrix = env.executor.build_match_matrix(env.state)
    chosen = RuleBasedScheduler(env.executor).select_assignment(matrix)
    if chosen is None:
        return obs["noop_index"]
    return chosen.subtask_index * len(matrix.resource_ids) + chosen.resource_index


def pick_random(obs: dict, rng: random.Random) -> int:
    """先从合法的分配动作中随机选择；无可分配动作再等待。"""
    valid = [i for i, v in enumerate(obs["action_mask"][:-1]) if v]
    return rng.choice(valid) if valid else obs["noop_index"]


def run(policy: str) -> None:
    env = create_env()
    obs, info = env.reset()
    rng = random.Random(0)
    total_reward = 0.0
    print(f"\n=== {policy} 策略 ===")
    for _ in range(env.max_steps):
        action = pick_rule(env, obs) if policy == "规则" else pick_random(obs, rng)
        action_label = obs["action_labels"][action]
        obs, reward, terminated, truncated, info = env.step(action)
        total_reward += reward
        print(
            f"t={info['time']:5.2f}s | {action_label} | "
            f"结束任务={info['completed']} | 奖励={reward:+.3f}"
        )
        if terminated or truncated:
            break
    print(
        f"结果={info['status']}  完成率={info['completion_rate']:.0%}  "
        f"能耗估计={info['total_energy']:.2f}  累计奖励={total_reward:+.3f}"
    )


if __name__ == "__main__":
    run("规则")
    run("随机")
    print("\n说明：仅为接口联通示例，不代表MAPPO训练或算法性能对比。")
