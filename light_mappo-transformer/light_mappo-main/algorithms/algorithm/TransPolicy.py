import torch
import torch.nn as nn
import torch.nn.functional as F
import math

from algorithms.utils.distributions import FixedCategorical


# FixedCategorical定义 - 与源代码适配



class AutoregressiveTransformerPolicy(nn.Module):
    def __init__(self, state_dim, max_action_value=20, hidden_dim=128, nhead=8, num_layers=3,
                 dropout=0.1, max_seq_len=50, use_orthogonal=True, gain=0.01):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.max_action_value = max_action_value
        self.max_seq_len = max_seq_len

        # 初始化方法
        init_method = [nn.init.xavier_uniform_, nn.init.orthogonal_][use_orthogonal]

        def init_(m):
            return self._init_weights(m, init_method, lambda x: nn.init.constant_(x, 0), gain)

        # 状态编码器
        self.state_encoder = init_(nn.Linear(state_dim, hidden_dim))

        # 动作嵌入
        self.action_embed = nn.Embedding(max_action_value + 1, hidden_dim)  # +1 for start token

        # 位置嵌入
        self.position_embed = nn.Embedding(max_seq_len, hidden_dim)

        # Transformer解码器
        decoder_layer = nn.TransformerDecoderLayer(
            d_model=hidden_dim, nhead=nhead, dim_feedforward=hidden_dim * 4,
            dropout=dropout, batch_first=True
        )
        self.transformer = nn.TransformerDecoder(decoder_layer, num_layers)

        # 输出头
        self.output_head = init_(nn.Linear(hidden_dim, max_action_value))

        # 特殊token
        self.START_TOKEN = 0

    def _init_weights(self, m, init_method, bias_init, gain):
        if isinstance(m, nn.Linear):
            init_method(m.weight, gain=gain)
            bias_init(m.bias)
        return m

    def forward(self, state, action_dims, available_actions=None):
        batch_size = state.size(0)
        device = state.device
        num_steps = len(action_dims)

        # 编码状态
        state_encoded = self.state_encoder(state).unsqueeze(1)  # [B, 1, hidden_dim]

        # 结果列表
        distributions = []

        # 当前动作序列
        current_actions = torch.full((batch_size, 1), self.START_TOKEN, dtype=torch.long, device=device)

        # 自回归生成
        for step in range(num_steps):
            # 动作嵌入
            action_embeds = self.action_embed(current_actions)  # [B, seq_len, hidden_dim]

            # 位置嵌入
            seq_len = current_actions.size(1)
            positions = torch.arange(seq_len, device=device).unsqueeze(0).expand(batch_size, -1)
            pos_embeds = self.position_embed(positions)

            # 组合嵌入
            input_embeds = action_embeds + pos_embeds

            # 因果掩码
            causal_mask = torch.triu(torch.ones(seq_len, seq_len, device=device), diagonal=1).bool()

            # Transformer解码
            output = self.transformer(
                tgt=input_embeds,
                memory=state_encoded,
                tgt_mask=causal_mask
            )

            # 获取最后位置的输出
            last_hidden = output[:, -1, :]  # [B, hidden_dim]

            # 计算logits
            full_logits = self.output_head(last_hidden)  # [B, max_action_value]

            # 截取到当前动作维度
            logits = full_logits[:, :action_dims[step]]

            # 应用可用动作掩码
            if available_actions is not None and step < len(available_actions[0]):
                step_masks = []
                for batch_actions in available_actions:
                    if step < len(batch_actions):
                        a = batch_actions[step]
                        step_masks.append(a)
                    else:
                        step_masks.append([1] * action_dims)

                # 应用掩码
                step_masks = torch.tensor(step_masks, device=logits.device, dtype=torch.float32)
                logits = logits.masked_fill(step_masks == 0, -1e10)


            # 创建FixedCategorical分布
            dist = FixedCategorical(logits=logits)
            distributions.append(dist)

            # 采样下一个动作（用于下一步的输入）
            if step < num_steps - 1:
                next_action = dist.sample().squeeze(-1)  # [B]
                current_actions = torch.cat([current_actions, next_action.unsqueeze(1)], dim=1)

        return distributions


# 使用示例
if __name__ == "__main__":
    # 创建模型
    model = AutoregressiveTransformerPolicy(
        state_dim=64,
        max_action_value=10,
        hidden_dim=128
    )

    batch_size = 4
    state = torch.randn(batch_size, 64)

    # 测试不同的动作空间
    action_dims = [3, 4, 2]  # 3个动作维度，大小分别为3,4,2

    # 创建可用动作掩码
    available_actions = [torch.ones(batch_size, dim) for dim in action_dims]

    # 前向传播
    distributions = model(state, action_dims, available_actions)

    print(f"返回{len(distributions)}个FixedCategorical分布")

    # 使用分布
    for i, dist in enumerate(distributions):
        print(f"第{i + 1}个动作维度(大小={action_dims[i]}):")
        print(f"  logits形状: {dist.logits.shape}")
        print(f"  采样结果: {dist.sample()[:2].tolist()}")  # [B, 1]
        print(f"  mode结果: {dist.mode()[:2].tolist()}")  # [B, 1]

    # 演示自回归过程
    print("\n自回归采样演示:")
    sampled_actions = []
    for i, dist in enumerate(distributions):
        action = dist.sample()
        sampled_actions.append(action)
        print(f"第{i + 1}步: 基于前{i}步的动作选择第{i + 1}个维度的动作")

    print(f"最终动作序列: {[action.squeeze(-1).tolist() for action in sampled_actions]}")