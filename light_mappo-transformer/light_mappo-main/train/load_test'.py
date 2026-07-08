"""
# @Time    : 2021/6/30 10:07 下午
# @Author  : hezhiqiang
# @Email   : tinyzqh@163.com
# @File    : train.py
"""
import random
import sys
import os
import socket
import time
import setproctitle
import numpy as np
from pathlib import Path
import torch
import matplotlib.pyplot as plt
from algorithms.algorithm.r_actor_critic import R_Actor
from envs import env_core

parent_dir = os.path.abspath(os.path.join(os.getcwd(), "."))
sys.path.append(parent_dir)

from config import get_config
from envs.env_wrappers import DummyVecEnv


def UAV_cost(s):
    if s == 0:
        return 5
    if s == 1:
        return 10
    if s == 2:
        return 25
    if s == 3:
        return 0


def UAV_finished(t, ob, w):
    if t == 3:
        return 0
    if ob == 0:
        return 0
    if ob == 1:
        if t == 1:
            return 1
        else:
            if t == 2:
                return 0
            if t == 0:
                if w < 2:
                    return 1
                else:
                    return 0
    if ob == 2:
        if t == 2:
            return 1
        else:
            return 0


def make_train_env(all_args):
    def get_env_fn(rank):
        def init_env():
            from envs.env_discrete import MultiDiscrete
            env = MultiDiscrete([[0, 4], [0, 2]])
            env.seed(all_args.seed + rank * 1000)
            return env

        return init_env

    return DummyVecEnv([get_env_fn(i) for i in range(all_args.n_rollout_threads)])


def make_eval_env(all_args):
    def get_env_fn(rank):
        def init_env():
            from envs.env_discrete import MultiDiscrete
            env = MultiDiscrete([[0, 8], [0, 9], [0, 8]])
            env.seed(all_args.seed + rank * 1000)
            return env

        return init_env

    return DummyVecEnv([get_env_fn(i) for i in range(all_args.n_rollout_threads)])


def parse_args(args, parser):
    parser.add_argument("--scenario_name", type=str, default="5tasks2UAVs", help="Which scenario to run on")
    parser.add_argument("--num_landmarks", type=int, default=3)
    parser.add_argument("--num_agents", type=int, default=2, help="number of players")
    all_args = parser.parse_known_args(args)[0]
    return all_args


def main(args):
    parser = get_config()
    all_args = parse_args(args, parser)

    if all_args.algorithm_name == "rmappo":
        assert all_args.use_recurrent_policy or all_args.use_naive_recurrent_policy, "check recurrent policy!"
    elif all_args.algorithm_name == "mappo":
        assert (
                all_args.use_recurrent_policy == False and all_args.use_naive_recurrent_policy == False
        ), "check recurrent policy!"
    else:
        raise NotImplementedError

    assert (
                   all_args.share_policy == True and all_args.scenario_name == "simple_speaker_listener"
           ) == False, "The simple_speaker_listener scenario can not use shared policy. Please check the config.py."

    # 设备设置
    if all_args.cuda and torch.cuda.is_available():
        print("choose to use gpu...")
        device = torch.device("cuda:0")
        torch.set_num_threads(all_args.n_training_threads)
        if all_args.cuda_deterministic:
            torch.backends.cudnn.benchmark = False
            torch.backends.cudnn.deterministic = True
    else:
        print("choose to use cpu...")
        device = torch.device("cpu")
        torch.set_num_threads(all_args.n_training_threads)

    setproctitle.setproctitle(
        str(all_args.algorithm_name)
        + "-"
        + str(all_args.env_name)
        + "-"
        + str(all_args.experiment_name)
        + "@"
        + str(all_args.user_name)
    )

    # 随机种子
    torch.manual_seed(all_args.seed)
    torch.cuda.manual_seed_all(all_args.seed)
    np.random.seed(all_args.seed)

    # 环境初始化
    envs = make_train_env(all_args)
    num_agents = all_args.num_agents

    config = {
        "all_args": all_args,
        "envs": envs,
        "num_agents": num_agents,
        "device": device,
    }

    # 加载模型
    actor0 = R_Actor(config["all_args"], config["envs"].observation_space[0],
                     config["envs"].action_space[0], device=config["device"])
    project_root = Path(__file__).resolve().parents[1]
    policy_actor_state_dict = torch.load(
        str(project_root / "results/MyEnv/5tasks2UAVs/mappo/check/run2/models/actor_agent0.pt"),
        map_location=torch.device('cpu')
    )
...
    project_root = Path(__file__).resolve().parents[1]
    policy_actor_state_dict = torch.load(
        str(project_root / "results/MyEnv/5tasks2UAVs/mappo/check/run2/models/actor_agent1.pt"),
        map_location=torch.device('cpu')
    )
    actor1.load_state_dict(policy_actor_state_dict)

    # 解析C++传递的参数
    # 参数格式: agent0_obs(7个值) + agent1_obs(7个值) +
    #          agent0_available_actions0(5个值) + agent0_available_actions1(4个值) +
    #          agent1_available_actions0(5个值) + agent1_available_actions1(4个值)
    args_data = list(map(float, args))

    # 解析观测数据
    agent_obs = [
        args_data[0:7],  # agent0的观测
        args_data[7:14]  # agent1的观测
    ]

    # 解析可用动作
    ptr = 14
    available_actions = [
        [
            args_data[ptr:ptr + 5],  # agent0的第一个动作维度可用掩码
            args_data[ptr + 5:ptr + 9]  # agent0的第二个动作维度可用掩码
        ],
        [
            args_data[ptr + 9:ptr + 14],  # agent1的第一个动作维度可用掩码
            args_data[ptr + 14:ptr + 18]  # agent1的第二个动作维度可用掩码
        ]
    ]

    # 转换为合适的类型
    agent_obs = [np.array(obs, dtype=np.float32) for obs in agent_obs]
    available_actions = [
        [np.array(aa0, dtype=np.float32), np.array(aa1, dtype=np.float32)]
        for aa0, aa1 in available_actions
    ]

    # 单次推理
    actions0, _, _ = actor0(
        np.array([agent_obs[0]]),
        np.zeros(64),
        np.ones(10),
        [available_actions[0]]
    )
    actions1, _, _ = actor1(
        np.array([agent_obs[1]]),
        np.zeros(64),
        np.ones(10),
        [available_actions[1]]
    )

    # 输出结果（格式: actions0[0][0] actions0[0][1] actions1[0][0] actions1[0][1]）
    print(f"{actions0[0][0].item()} {actions0[0][1].item()} {actions1[0][0].item()} {actions1[0][1].item()}")


if __name__ == "__main__":
    main(sys.argv[1:])