"""
# @Time    : 2021/7/1 6:53 下午
# @Author  : hezhiqiang01
# @Email   : hezhiqiang01@baidu.com
# @File    : r_actor_critic.py
"""

import torch
from torch import nn
from torch.nn.functional import embedding

from algorithms.utils.util import init, check
from algorithms.utils.cnn import CNNBase
from algorithms.utils.mlp import MLPBase
from algorithms.utils.rnn import RNNLayer
from algorithms.utils.act import ACTLayer
from algorithms.utils.popart import PopArt
from utils.util import get_shape_from_obs_space
# from algorithms.algorithm import positionencoding
from algorithms.algorithm import encoder

class R_Actor(nn.Module):
    """
    Actor network class for MAPPO. Outputs actions given observations.
    :param args: (argparse.Namespace) arguments containing relevant model information.
    :param obs_space: (gym.Space) observation space.
    :param action_space: (gym.Space) action space.
    :param device: (torch.device) specifies the device to run on (cpu/gpu).
    """
    def __init__(self, args, obs_space, action_space, device=torch.device("cpu")):
        super(R_Actor, self).__init__()
        self.hidden_size = args.hidden_size

        self._gain = args.gain
        self._use_orthogonal = args.use_orthogonal
        self._use_policy_active_masks = args.use_policy_active_masks
        self._use_naive_recurrent_policy = args.use_naive_recurrent_policy
        self._use_recurrent_policy = args.use_recurrent_policy
        self._recurrent_N = args.recurrent_N
        self.tpdv = dict(dtype=torch.float32, device=device)

        obs_shape = get_shape_from_obs_space(obs_space)
        print(obs_shape[0])
        # base = CNNBase if len(obs_shape) == 3 else MLPBase

#多头注意力机制
        # self.embedding = torch.nn.Embedding(4,128)
        # self.MultiheadAttention = torch.nn.MultiheadAttention(128,8,batch_first=True)
        # self.PE = positionencoding.PositionalEncoding(128,20)
        self.Attn2Linear = torch.nn.Linear(128,64)
        self.gelu = torch.nn.GELU()

        self.encoder = encoder.Encoder(21, 20, 128, 256,8,6,0,device=device)


        # self.base = base(args, obs_shape)

        if self._use_naive_recurrent_policy or self._use_recurrent_policy:
            self.rnn = RNNLayer(self.hidden_size, self.hidden_size, self._recurrent_N, self._use_orthogonal)

        self.act = ACTLayer(action_space, self.hidden_size, self._use_orthogonal, self._gain)

        self.to(device)

    def forward(self, obs, rnn_states, masks, available_actions=None, deterministic=False):
        """
        Compute actions from the given inputs.
        :param obs: (np.ndarray / torch.Tensor) observation inputs into network.
        :param rnn_states: (np.ndarray / torch.Tensor) if RNN network, hidden states for RNN.
        :param masks: (np.ndarray / torch.Tensor) mask tensor denoting if hidden states should be reinitialized to zeros.
        :param available_actions: (np.ndarray / torch.Tensor) denotes which actions are available to agent
                                                              (if None, all actions available)
        :param deterministic: (bool) whether to sample from action distribution or return the mode.

        :return actions: (torch.Tensor) actions to take.
        :return action_log_probs: (torch.Tensor) log probabilities of taken actions.
        :return rnn_states: (torch.Tensor) updated RNN hidden states.
        """
        # print("masks shape:", masks.shape)  # 输出形状
        # print("masks dtype:", masks.dtype)  # 输出数据类型
        # print("masks sample:", masks)  # 输出前两个样本的值
        # print("obs shape:", obs.shape)  # 输出形状
        # print("obs dtype:", obs.dtype)  # 输出数据类型
        # print("obs sample:", obs)  # 输出前两个样本的值
        # print("rnn_states shape:", rnn_states.shape)  # 输出形状
        # print("rnn_states dtype:", rnn_states.dtype)  # 输出数据类型
        # print("rnn_states sample:", rnn_states)  # 输出前两个样本的值
        obs = check(obs).to(**self.tpdv)
        rnn_states = check(rnn_states).to(**self.tpdv)
        masks = check(masks).to(**self.tpdv)
        # if available_actions is not None:
        #     available_actions = check(available_actions).to(**self.tpdv)

        # actor_features = self.base(obs)
        # 全连接层
        # actor_features = self.fc(obs)
        # actor_features = self.relu(actor_features)

        #多头注意力
        obs_longtensor = obs.long()
        # obs_embedding = self.embedding(obs_longtensor)
        # obs_embedding = self.PE(obs_embedding)
        # attn_output,attn_weights = self.MultiheadAttention(obs_embedding,obs_embedding,obs_embedding)
        # attn_output += + obs_embedding
        attn_output = self.encoder(obs_longtensor,None)
        attn_output_pool = torch.mean(attn_output,dim=1)
        actor_features = self.Attn2Linear(attn_output_pool)
        actor_features = self.gelu(actor_features)


        if self._use_naive_recurrent_policy or self._use_recurrent_policy:
            actor_features, rnn_states = self.rnn(actor_features, rnn_states, masks)

        actions, action_log_probs = self.act(actor_features, available_actions, deterministic)

        return actions, action_log_probs, rnn_states

    def evaluate_actions(self, obs, rnn_states, action, masks, available_actions=None, active_masks=None):
        """
        Compute log probability and entropy of given actions.
        :param obs: (torch.Tensor) observation inputs into network.
        :param action: (torch.Tensor) actions whose entropy and log probability to evaluate.
        :param rnn_states: (torch.Tensor) if RNN network, hidden states for RNN.
        :param masks: (torch.Tensor) mask tensor denoting if hidden states should be reinitialized to zeros.
        :param available_actions: (torch.Tensor) denotes which actions are available to agent
                                                              (if None, all actions available)
        :param active_masks: (torch.Tensor) denotes whether an agent is active or dead.

        :return action_log_probs: (torch.Tensor) log probabilities of the input actions.
        :return dist_entropy: (torch.Tensor) action distribution entropy for the given inputs.
        """

        obs = check(obs).to(**self.tpdv)
        rnn_states = check(rnn_states).to(**self.tpdv)
        action = check(action).to(**self.tpdv)
        masks = check(masks).to(**self.tpdv)
        if available_actions is not None:
            available_actions = check(available_actions).to(**self.tpdv)

        if active_masks is not None:
            active_masks = check(active_masks).to(**self.tpdv)

        # actor_features = self.base(obs)
        # actor_features = self.fc(obs)
        # actor_features = self.relu(actor_features)
        # 多头注意力
        obs_longtensor = obs.long()
        # obs_embedding = self.embedding(obs_longtensor)
        # obs_embedding = self.PE(obs_embedding)
        # attn_output,attn_weights = self.MultiheadAttention(obs_embedding, obs_embedding, obs_embedding)
        # attn_output += obs_embedding
        attn_output = self.encoder(obs_longtensor,None)
        attn_output_pool = torch.mean(attn_output, dim=1)
        actor_features = self.Attn2Linear(attn_output_pool)
        actor_features = self.gelu(actor_features)

        if self._use_naive_recurrent_policy or self._use_recurrent_policy:
            actor_features, rnn_states = self.rnn(actor_features, rnn_states, masks)

        action_log_probs, dist_entropy = self.act.evaluate_actions(actor_features,
                                                                   action, available_actions,
                                                                   active_masks=
                                                                   active_masks if self._use_policy_active_masks
                                                                   else None)

        return action_log_probs, dist_entropy


class R_Critic(nn.Module):
    """
    Critic network class for MAPPO. Outputs value function predictions given centralized input (MAPPO) or
                            local observations (IPPO).
    :param args: (argparse.Namespace) arguments containing relevant model information.
    :param cent_obs_space: (gym.Space) (centralized) observation space.
    :param device: (torch.device) specifies the device to run on (cpu/gpu).
    """
    def __init__(self, args, cent_obs_space, device=torch.device("cpu")):
        super(R_Critic, self).__init__()
        self.hidden_size = args.hidden_size
        self._use_orthogonal = args.use_orthogonal
        self._use_naive_recurrent_policy = args.use_naive_recurrent_policy
        self._use_recurrent_policy = args.use_recurrent_policy
        self._recurrent_N = args.recurrent_N
        self._use_popart = args.use_popart
        self.tpdv = dict(dtype=torch.float32, device=device)
        init_method = [nn.init.xavier_uniform_, nn.init.orthogonal_][self._use_orthogonal]

        cent_obs_shape = get_shape_from_obs_space(cent_obs_space)
        # base = CNNBase if len(cent_obs_shape) == 3 else MLPBase
        print(cent_obs_shape[0])

        # self.base = base(args, cent_obs_shape)
    #多头注意力机制
        # self.embedding = torch.nn.Embedding(4, 128)
        # self.MultiheadAttention = torch.nn.MultiheadAttention(128, 8,batch_first=True)
        # self.PE = positionencoding.PositionalEncoding(128, 100)
        self.Attn2Linear = torch.nn.Linear(128, 64)
        self.gelu = torch.nn.GELU()
        self.encoder = encoder.Encoder(21, 30, 128, 256,8,6,0.1,device=device)



        if self._use_naive_recurrent_policy or self._use_recurrent_policy:
            self.rnn = RNNLayer(self.hidden_size, self.hidden_size, self._recurrent_N, self._use_orthogonal)

        def init_(m):
            return init(m, init_method, lambda x: nn.init.constant_(x, 0))

        if self._use_popart:
            self.v_out = init_(PopArt(self.hidden_size, 1, device=device))
        else:
            self.v_out = init_(nn.Linear(self.hidden_size, 1))

        self.to(device)

    def forward(self, cent_obs, rnn_states, masks):
        """
        Compute actions from the given inputs.
        :param cent_obs: (np.ndarray / torch.Tensor) observation inputs into network.
        :param rnn_states: (np.ndarray / torch.Tensor) if RNN network, hidden states for RNN.
        :param masks: (np.ndarray / torch.Tensor) mask tensor denoting if RNN states should be reinitialized to zeros.

        :return values: (torch.Tensor) value function predictions.
        :return rnn_states: (torch.Tensor) updated RNN hidden states.
        """
        cent_obs = check(cent_obs).to(**self.tpdv)
        rnn_states = check(rnn_states).to(**self.tpdv)
        masks = check(masks).to(**self.tpdv)

        # critic_features = self.base(cent_obs)
        # critic_features = self.fc(cent_obs)
        # critic_features = self.relu(critic_features)

        #多头注意力机制
        cent_obs_embedding = cent_obs.long()
        # cent_obs_embedding = self.embedding(cent_obs_embedding)
        # cent_obs_embedding = self.PE(cent_obs_embedding)
        # attn_output,attn_weights = self.MultiheadAttention(cent_obs_embedding,cent_obs_embedding,cent_obs_embedding)
        # attn_output += cent_obs_embedding


        attn_output = self.encoder(cent_obs_embedding,None)
        attn_output_pooled = torch.mean(attn_output, dim=1)
        critic_features = self.Attn2Linear(attn_output_pooled)
        critic_features = self.gelu(critic_features)


        if self._use_naive_recurrent_policy or self._use_recurrent_policy:
            critic_features, rnn_states = self.rnn(critic_features, rnn_states, masks)
        values = self.v_out(critic_features)

        return values, rnn_states
