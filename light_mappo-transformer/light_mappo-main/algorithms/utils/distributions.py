import numpy as np
import torch
import torch.nn as nn
from sympy import pprint

from .util import init

"""
Modify standard PyTorch distributions so they to make compatible with this codebase. 
"""

#
# Standardize distribution interfaces
#

# Categorical
class FixedCategorical(torch.distributions.Categorical):
    def sample(self):
        return super().sample().unsqueeze(-1)

    def log_probs(self, actions):
        return (
            super()
            .log_prob(actions.squeeze(-1))
            .view(actions.size(0), -1)
            .sum(-1)
            .unsqueeze(-1)
        )

    def mode(self):
        return self.probs.argmax(dim=-1, keepdim=True)


# Normal
class FixedNormal(torch.distributions.Normal):
    def log_probs(self, actions):
        return super().log_prob(actions).sum(-1, keepdim=True)

    def entrop(self):
        return super.entropy().sum(-1)

    def mode(self):
        return self.mean


# Bernoulli
class FixedBernoulli(torch.distributions.Bernoulli):
    def log_probs(self, actions):
        return super.log_prob(actions).view(actions.size(0), -1).sum(-1).unsqueeze(-1)

    def entropy(self):
        return super().entropy().sum(-1)

    def mode(self):
        return torch.gt(self.probs, 0.5).float()


class Categorical(nn.Module):
    def __init__(self, num_inputs, num_outputs, use_orthogonal=True, gain=0.01):
        super(Categorical, self).__init__()
        init_method = [nn.init.xavier_uniform_, nn.init.orthogonal_][use_orthogonal]
        def init_(m):
            return init(m, init_method, lambda x: nn.init.constant_(x, 0), gain)

        self.linear = init_(nn.Linear(num_inputs, num_outputs))

    def forward(self, x, available_actions=None):
        x = self.linear(x)
        if available_actions is not None:
            x[available_actions == 0] = -1e10
        return FixedCategorical(logits=x)


# 基于多头自注意力的动作分类器
# class Categorical(nn.Module):
#     def __init__(self, num_inputs, num_outputs, use_orthogonal=True, gain=0.01):
#         super(Categorical, self).__init__()
#         self.state_proj = nn.Linear(num_inputs, 128)
#         self.action_embed = nn.Parameter(torch.randn(1,128))
#         nn.init.normal_(self.action_embed, mean=0, std=0.02)
#         self.attention = torch.nn.MultiheadAttention(128, 8, batch_first=True)
#         self.classifier = nn.Sequential(
#             nn.Linear(128, 128),
#             nn.ReLU(),
#             nn.Linear(128, 1)
#         )
#         self.action_dim = num_outputs
#
#     def forward(self, x, available_actions=None):
#         state_emb = self.state_proj(x)
#         state_2d = state_emb.unsqueeze(1)
#         pooled = nn.functional.adaptive_avg_pool1d(state_2d, self.action_dim)
#         pooled = pooled.transpose(1, 2)
#         queries = pooled * self.action_embed
#         state_emb_expanded = state_emb.unsqueeze(1)
#         attn_output, _ = self.attention(
#             query=queries,
#             key=state_emb_expanded,
#             value=state_emb_expanded
#         )
#         x = self.classifier(attn_output+queries).squeeze(-1)
#         if available_actions is not None:
#             x[available_actions == 0] = -1e10
#         return FixedCategorical(logits=x)



class SequentialTransformerPolicy(nn.Module):
    def __init__(self, state_dim, action_dims, hidden_dim=128, nhead=4, num_layers=2):
        super().__init__()
        self.action_dims = action_dims  # e.g., [3, 4, 2] for MultiDiscrete([3,4,2])
        self.num_actions = len(action_dims)

        self.state_proj = nn.Linear(state_dim, hidden_dim)
        self.token_embed = nn.Embedding(self.num_actions + 1, hidden_dim)  # +1 for BOS
        self.position_embed = nn.Parameter(torch.randn(self.num_actions + 1, hidden_dim))

        encoder_layer = nn.TransformerDecoderLayer(d_model=hidden_dim, nhead=nhead, batch_first=True)
        self.transformer = nn.TransformerDecoder(encoder_layer, num_layers=num_layers)

        self.output_heads = nn.ModuleList([
            nn.Linear(hidden_dim, dim) for dim in action_dims
        ])

    def forward(self, state):
        B = state.size(0)
        state_enc = self.state_proj(state).unsqueeze(1)  # [B, 1, hidden_dim]

        tokens = torch.arange(self.num_actions + 1, device=state.device).unsqueeze(0).repeat(B, 1)
        token_embeddings = self.token_embed(tokens) + self.position_embed[:self.num_actions+1]

        tgt_mask = torch.triu(torch.ones(self.num_actions + 1, self.num_actions + 1, device=state.device), diagonal=1).bool()

        transformer_output = self.transformer(
            tgt=token_embeddings,
            memory=state_enc,
            tgt_mask=tgt_mask
        )

        logits = []
        for i in range(self.num_actions):
            logit = self.output_heads[i](transformer_output[:, i+1])
            logits.append(logit)

        return logits  # list of [B, action_dim_i] tensors


class DiagGaussian(nn.Module):
    def __init__(self, num_inputs, num_outputs, use_orthogonal=True, gain=0.01):
        super(DiagGaussian, self).__init__()

        init_method = [nn.init.xavier_uniform_, nn.init.orthogonal_][use_orthogonal]
        def init_(m): 
            return init(m, init_method, lambda x: nn.init.constant_(x, 0), gain)

        self.fc_mean = init_(nn.Linear(num_inputs, num_outputs))
        self.logstd = AddBias(torch.zeros(num_outputs))

    def forward(self, x):
        action_mean = self.fc_mean(x)

        #  An ugly hack for my KFAC implementation.
        zeros = torch.zeros(action_mean.size())
        if x.is_cuda:
            zeros = zeros.cuda()

        action_logstd = self.logstd(zeros)
        return FixedNormal(action_mean, action_logstd.exp())


class Bernoulli(nn.Module):
    def __init__(self, num_inputs, num_outputs, use_orthogonal=True, gain=0.01):
        super(Bernoulli, self).__init__()
        init_method = [nn.init.xavier_uniform_, nn.init.orthogonal_][use_orthogonal]
        def init_(m): 
            return init(m, init_method, lambda x: nn.init.constant_(x, 0), gain)
        
        self.linear = init_(nn.Linear(num_inputs, num_outputs))

    def forward(self, x):
        x = self.linear(x)
        return FixedBernoulli(logits=x)

class AddBias(nn.Module):
    def __init__(self, bias):
        super(AddBias, self).__init__()
        self._bias = nn.Parameter(bias.unsqueeze(1))

    def forward(self, x):
        if x.dim() == 2:
            bias = self._bias.t().view(1, -1)
        else:
            bias = self._bias.t().view(1, -1, 1, 1)

        return x + bias

