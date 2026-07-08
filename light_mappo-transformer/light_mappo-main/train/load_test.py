"""
# @Time    : 2021/6/30 10:07 下午
# @Author  : hezhiqiang
# @Email   : tinyzqh@163.com
# @File    : train.py
"""

# !/usr/bin/env python
import sys
import os
import socket
import setproctitle
import numpy as np
from pathlib import Path
import torch

from algorithms.algorithm.r_actor_critic import R_Actor

# Get the parent directory of the current file
parent_dir = os.path.abspath(os.path.join(os.getcwd(), "."))

# Append the parent directory to sys.path, otherwise the following import will fail
sys.path.append(parent_dir)

from config import get_config
from envs.env_wrappers import DummyVecEnv

"""Train script for MPEs."""


def make_train_env(all_args):
    def get_env_fn(rank):
        def init_env():
            # TODO 注意注意，这里选择连续还是离散可以选择注释上面两行，或者下面两行。
            # TODO Important, here you can choose continuous or discrete action space by uncommenting the above two lines or the below two lines.

            # from envs.env_continuous import ContinuousActionEnv
            #
            # env = ContinuousActionEnv()

            # from envs.env_discrete import DiscreteActionEnv
            #
            # env = DiscreteActionEnv()
            from envs.env_discrete import MultiDiscrete
            env = MultiDiscrete([[0,4],[0,2]])

            env.seed(all_args.seed + rank * 1000)
            return env

        return init_env

    return DummyVecEnv([get_env_fn(i) for i in range(all_args.n_rollout_threads)])


def make_eval_env(all_args):
    def get_env_fn(rank):
        def init_env():
            # TODO 注意注意，这里选择连续还是离散可以选择注释上面两行，或者下面两行。
            # TODO Important, here you can choose continuous or discrete action space by uncommenting the above two lines or the below two lines.
            # from envs.env_continuous import ContinuousActionEnv
            #
            # env = ContinuousActionEnv()
            # from envs.env_discrete import DiscreteActionEnv
            # env = DiscreteActionEnv()
            from envs.env_discrete import MultiDiscrete
            env = MultiDiscrete([[0,8],[0,9],[0,8]])
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

    # cuda
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

    # run dir
    # run_dir = (
    #     Path(os.path.split(os.path.dirname(os.path.abspath(__file__)))[0] + "/results")
    #     / all_args.env_name
    #     / all_args.scenario_name
    #     / all_args.algorithm_name
    #     / all_args.experiment_name
    # )
    # if not run_dir.exists():
    #     os.makedirs(str(run_dir))
    #
    # if not run_dir.exists():
    #     curr_run = "run1"
    # else:
    #     exst_run_nums = [
    #         int(str(folder.name).split("run")[1])
    #         for folder in run_dir.iterdir()
    #         if str(folder.name).startswith("run")
    #     ]
    #     if len(exst_run_nums) == 0:
    #         curr_run = "run1"
    #     else:
    #         curr_run = "run%i" % (max(exst_run_nums) + 1)
    # run_dir = run_dir / curr_run
    # if not run_dir.exists():
    #     os.makedirs(str(run_dir))

    setproctitle.setproctitle(
        str(all_args.algorithm_name)
        + "-"
        + str(all_args.env_name)
        + "-"
        + str(all_args.experiment_name)
        + "@"
        + str(all_args.user_name)
    )

    # seed
    torch.manual_seed(all_args.seed)
    torch.cuda.manual_seed_all(all_args.seed)
    np.random.seed(all_args.seed)

    # env init
    envs = make_train_env(all_args)
    eval_envs = make_eval_env(all_args) if all_args.use_eval else None
    num_agents = all_args.num_agents

    config = {
        "all_args": all_args,
        "envs": envs,
        "eval_envs": eval_envs,
        "num_agents": num_agents,
        "device": device,
        # "run_dir": run_dir,
    }

    import algorithms.algorithm.r_actor_critic
    actor0 = R_Actor(config["all_args"],config["envs"].observation_space[0],config["envs"].action_space[0],device=config["device"])
    project_root = Path(__file__).resolve().parents[1]
    policy_actor_state_dict = torch.load(str(project_root / "results/MyEnv/5tasks2UAVs/mappo/check/run14/models/actor_agent0.pt"))
    actor0.load_state_dict(policy_actor_state_dict)
    actor1 = R_Actor(config["all_args"], config["envs"].observation_space[0], config["envs"].action_space[0],
                     device=config["device"])
    policy_actor_state_dict = torch.load(str(project_root / "results/MyEnv/5tasks2UAVs/mappo/check/run14/models/actor_agent1.pt"))
    actor1.load_state_dict(policy_actor_state_dict)

    obs = np.array([[1,0,0,0,0,0,0,0,0,0,0,0,2,1,1]])
    actions0, action_log_probs, rnn_states = actor0(obs,np.zeros(64),np.ones(10),[[[1,0,0,0,1],[1,1,1,1]]])
    actions1, action_log_probs, rnn_states = actor1(obs, np.zeros(64), np.ones(10),[[[1,0,0,0,1],[1,1,1,1]]])
    print(actions0,actions1)
    # action_log_probs, dist_entropy = actor0.evaluate_actions(obs,np.zeros(64),np.array([[1,0],[1,1],[1,2],[0,0],[0,1],[0,2],[2,0],[2,1],[2,2],[4,0],[4,1],[4,2]]),np.ones(6))
    # print(action_log_probs)
    # actions0, action_log_probs, rnn_states = actor0(obs, np.zeros(64), np.ones(6))
    # actions1, action_log_probs, rnn_states = actor1(obs, np.zeros(64), np.ones(6))
    # print(actions0, actions1)
    # actions0, action_log_probs, rnn_states = actor0(obs, np.zeros(64), np.ones(6))
    # actions1, action_log_probs, rnn_states = actor1(obs, np.zeros(64), np.ones(6))
    # print(actions0, actions1)
    # actions0, action_log_probs, rnn_states = actor0(obs, np.zeros(64), np.ones(6))
    # actions1, action_log_probs, rnn_states = actor1(obs, np.zeros(64), np.ones(6))
    # print(actions0, actions1)
    # run experiments
    # if all_args.share_policy:
    #     from runner.shared.env_runner import EnvRunner as Runner
    # else:
    #     from runner.separated.env_runner import EnvRunner as Runner

    # runner = Runner(config)
    # runner.run()
    #
    # # post process
    # envs.close()
    # if all_args.use_eval and eval_envs is not envs:
    #     eval_envs.close()
    #
    # runner.writter.export_scalars_to_json(str(runner.log_dir + "/summary.json"))
    # runner.writter.close()

    b = actions0.tolist()
    print(b[0])
if __name__ == "__main__":
    main(sys.argv[1:])
