import sys
import os
import numpy as np
import torch
from pathlib import Path

from algorithms.algorithm.r_actor_critic import R_Actor
from config import get_config
from envs.env_wrappers import DummyVecEnv

# 设置项目根目录到搜索路径（使用更可靠的路径拼接）
current_dir = Path(__file__).resolve().parent
parent_dir = str(current_dir.parent)  # 根据根据实际文件所在目录的父目录
if parent_dir not in sys.path:
    sys.path.append(parent_dir)


def make_env(all_args):
    """创建环境（用于获取状态空间和动作空间）"""

    def get_env_fn(rank):
        def init_env():
            from envs.env_discrete import MultiDiscrete
            env = MultiDiscrete([[0, 4], [0, 2]])  # 与原训练环境保持一致
            env.seed(all_args.seed + rank * 1000)
            return env

        return init_env

    return DummyVecEnv([get_env_fn(i) for i in range(all_args.n_rollout_threads)])


def actor_inference(obs, rnn_states, available_actions,UAVid):
    """
    Actor网络推理函数
    :param obs: 观测数据，格式为numpy数组（如[[1,0,0,...]]）
    :param rnn_states: RNN隐藏状态，格式为numpy数组（如np.zeros(64)）
    :param available_actions: 可用动作掩码，格式为列表（如[[[1,0,0,0,1],[1,1,1,1]]]）
    :return: 两个智能体的动作
    """
    # 初始化配置
    parser = get_config()
    all_args = parser.parse_known_args([])[0]
    all_args.n_rollout_threads = 1  # 单线程推理
    all_args.seed = 123  # 固定随机种子

    # 设备配置（CPU）
    device = torch.device("cpu")
    torch.set_num_threads(1)

    # 初始化环境（仅用于获取状态和动作空间）
    envs = make_env(all_args)

    # 加载Actor网络
    actor0 = R_Actor(
        all_args,
        envs.observation_space[0],
        envs.action_space[0],
        device=device
    )


    # 加载预训练模型（使用Path动态获取路径）
    project_root = Path(__file__).resolve().parents[1]
    model_path0 = project_root / "weights" / "5UAVs" / f"actor_agent{UAVid-1}.pt"

    # 检查模型文件是否存在
    if not model_path0.exists():
        raise FileNotFoundError(f"模型文件不存在: {model_path0}")


    actor0.load_state_dict(torch.load(model_path0, map_location=device))

    # 设置为评估模式（禁用dropout等训练特有的层）
    actor0.eval()


    # 确保输入格式正确并添加批次维度（适配网络输入要求）
    obs = np.array(obs, dtype=np.float32)
    if obs.ndim == 1:
        obs = obs.reshape(1, -1)  # 确保至少是二维 (batch_size, obs_dim)

    rnn_states = np.array(rnn_states, dtype=np.float32)
    if rnn_states.ndim == 1:
        rnn_states = rnn_states.reshape(1, -1)  # 确保RNN状态带批次维度 (1, hidden_dim)

    # available_actions = np.array(available_actions, dtype=np.float32)

    # 推理（禁用梯度计算加速）
    with torch.no_grad():
        # 转换为torch张量并移动到设备
        # obs_tensor = torch.tensor(obs, device=device)
        # rnn_states_tensor = torch.tensor(rnn_states, device=device)
        # available_actions_tensor = torch.tensor(available_actions, device=device)
        #
        # # 掩码参数（与批次大小匹配，shape: (batch_size, 1)）
        # masks = torch.ones((obs.shape[0], 1), dtype=torch.float32, device=device)

        # 智能体推理
        actions0, _, _ = actor0(
            obs,
            np.zeros(64),
            np.ones(10),
            available_actions
        )

    # 清理环境资源
    envs.close()

    # 将张量转换为列表返回（展平动作输出）
    return [action.item() for action in actions0[0]]


# 测试示例
if __name__ == "__main__":
    try:
        # 测试输入（与原代码保持一致）
        test_obs = [[1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 1, 1]]
        test_rnn_states = np.zeros(64)
        test_available_actions = [[[1, 0, 0, 0, 1], [1, 1, 1, 1]]]

        # 调用推理函数
        actions0 = actor_inference(test_obs, test_rnn_states, test_available_actions)
        print("Agent0 动作:", actions0)

    except Exception as e:
        print(f"推理失败: {str(e)}")
        sys.exit(1)
