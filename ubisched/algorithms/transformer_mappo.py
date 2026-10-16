from __future__ import annotations

"""阶段6：结构化任务/资源Transformer Actor，复用第五阶段PPO与全局Critic。

每个UAV对自己资源作决定，任务数量/资源数量允许在容量上限内变化。
任务与资源作为独立token，不使用绝对位置编码；非法任务-资源动作仍由环境掩码约束。
"""

from typing import Dict, Mapping, Any, List
import torch
from torch import nn

from ubisched.algorithms.mappo_baseline import MAPPOBaseline, Transition
from ubisched.scheduling.multi_agent_env import MultiAgentSchedulerEnv


class TaskResourceTransformerActor(nn.Module):
    """联合注意力编码任务/资源，再为每个任务-资源组合计算动作得分。"""

    def __init__(self, task_dim: int, resource_dim: int, pair_dim: int,
                 max_tasks: int, max_resources: int, *, hidden: int = 64,
                 heads: int = 4, layers: int = 2):
        super().__init__()
        if hidden % heads:
            raise ValueError("hidden must be divisible by heads")
        self.max_tasks = max_tasks
        self.max_resources = max_resources
        self.task_embedding = nn.Sequential(nn.Linear(task_dim, hidden), nn.LayerNorm(hidden))
        self.resource_embedding = nn.Sequential(nn.Linear(resource_dim, hidden), nn.LayerNorm(hidden))
        self.type_embeddings = nn.Parameter(torch.zeros(2, hidden))
        layer = nn.TransformerEncoderLayer(
            d_model=hidden, nhead=heads, dim_feedforward=hidden * 2,
            dropout=0.0, activation="gelu", batch_first=True,
        )
        self.encoder = nn.TransformerEncoder(layer, num_layers=layers,
                                              enable_nested_tensor=False)
        self.pair_score = nn.Sequential(
            nn.Linear(hidden * 2 + pair_dim + 1 + 2, hidden),
            nn.Tanh(), nn.Linear(hidden, 1),
        )
        self.wait_score = nn.Sequential(
            nn.Linear(hidden * 2 + 2, hidden), nn.Tanh(), nn.Linear(hidden, 1)
        )

    @staticmethod
    def scaled_features(x: torch.Tensor):
        # 原数据含10^10量级的计算量；带符号log缩放防止注意力数值被大值淹没。
        return torch.sign(x) * torch.log1p(x.abs())

    def _embed_task_nodes(self, tasks: torch.Tensor,
                          structured: Mapping[str, torch.Tensor],
                          task_valid: torch.Tensor) -> torch.Tensor:
        """预留结构化任务依赖编码扩展点；原第六阶段行为保持不变。"""
        return self.task_embedding(self.scaled_features(tasks))

    def forward(self, structured: Mapping[str, torch.Tensor]) -> torch.Tensor:
        tasks = structured["tasks"]       # [B, T, Dt]
        resources = structured["resources"]  # [B, R, Dr]
        task_valid = structured["task_valid"].bool()
        resource_valid = structured["resource_valid"].bool()
        pair = structured["pairs"]
        urgency = structured["urgency"]
        context = structured["context"]
        if not task_valid.any(dim=-1).all() or not resource_valid.any(dim=-1).all():
            raise ValueError("At least one task and one resource per UAV are required")
        t = self._embed_task_nodes(tasks, structured, task_valid) + self.type_embeddings[0]
        r = self.resource_embedding(self.scaled_features(resources)) + self.type_embeddings[1]
        valid = torch.cat([task_valid, resource_valid], dim=1)
        encoded = self.encoder(torch.cat([t, r], dim=1),
                               src_key_padding_mask=~valid)
        h_t = encoded[:, :self.max_tasks]
        h_r = encoded[:, self.max_tasks:]
        B = tasks.shape[0]
        joint = torch.cat([
            h_t[:, :, None, :].expand(-1, -1, self.max_resources, -1),
            h_r[:, None, :, :].expand(-1, self.max_tasks, -1, -1),
            self.scaled_features(pair),
            urgency.unsqueeze(-1),
            context[:, None, None, :].expand(-1, self.max_tasks, self.max_resources, -1),
        ], dim=-1)
        pair_logits = self.pair_score(joint).squeeze(-1).reshape(B, -1)
        t_mean = (h_t * task_valid.unsqueeze(-1)).sum(dim=1) / task_valid.sum(dim=1, keepdim=True).clamp_min(1)
        r_mean = (h_r * resource_valid.unsqueeze(-1)).sum(dim=1) / resource_valid.sum(dim=1, keepdim=True).clamp_min(1)
        noop = self.wait_score(torch.cat([t_mean, r_mean, context], dim=-1))
        return torch.cat([pair_logits, noop], dim=-1)


class TransformerMAPPO(MAPPOBaseline):
    """共享Transformer Actor + 与MLP基线相同的PPO、团队奖励和集中式Critic。"""

    def __init__(self, env: MultiAgentSchedulerEnv, *, hidden: int = 64,
                 heads: int = 4, layers: int = 2,
                 coordinate_actions: bool = True, work_conserving: bool = True,
                 **kwargs) -> None:
        super().__init__(env, hidden=hidden, coordinate_actions=coordinate_actions,
                         work_conserving=work_conserving, **kwargs)
        obs, _ = env.reset()
        example = obs[env.agents[0]]
        self.actor = TaskResourceTransformerActor(
            len(example["task_features"][0]),
            len(example["resource_features"][0]),
            len(example["match_features"][0][0]),
            env.max_tasks, env.max_resources_per_uav,
            hidden=hidden, heads=heads, layers=layers,
        )
        self.optimizer = torch.optim.Adam(
            list(self.actor.parameters()) + list(self.critic.parameters()),
            lr=kwargs.get("lr", 3e-4),
        )
        self.actor_kind = "transformer"
        self.architecture = {"hidden": hidden, "heads": heads, "layers": layers}

    def _make_actor_inputs(self, env: MultiAgentSchedulerEnv, observations) -> Dict[str, torch.Tensor]:
        obs = [observations[a] for a in env.agents]
        result = {
            "tasks": torch.tensor([o["task_features"] for o in obs], dtype=torch.float32),
            "resources": torch.tensor([o["resource_features"] for o in obs], dtype=torch.float32),
            "pairs": torch.tensor([o["match_features"] for o in obs], dtype=torch.float32),
            "task_valid": torch.tensor([o["task_valid"] for o in obs], dtype=torch.bool),
            "resource_valid": torch.tensor([o["resource_valid"] for o in obs], dtype=torch.bool),
            "urgency": torch.tensor([
                [o["urgency_features"][i:i+env.max_resources_per_uav]
                 for i in range(0, env.noop_index, env.max_resources_per_uav)]
                for o in obs], dtype=torch.float32),
            "context": torch.tensor([
                [float(o["agent_index"]) / max(1, env.max_agents - 1),
                 float(o["time"]) / 1000.0] for o in obs], dtype=torch.float32),
        }
        if env.include_critical_path_features:
            result["critical_path_features"] = torch.tensor(
                [o["critical_path_features"] for o in obs], dtype=torch.float32)
        if env.include_dependency_features:
            result["dependency_features"] = torch.tensor(
                [o["dependency_features"] for o in obs], dtype=torch.float32)
            result["dependency_matrix"] = torch.tensor(
                [o["dependency_matrix"] for o in obs], dtype=torch.float32)
        return result

    def _actor_logits(self, flat_inputs, actor_inputs=None):
        if actor_inputs is None:
            raise ValueError("Transformer requires structured actor inputs")
        logits = self.actor(actor_inputs)
        if flat_inputs.ndim == 3:
            return logits.reshape(flat_inputs.shape[0], flat_inputs.shape[1], -1)
        return logits

    def _batch_actor_inputs(self, samples: List[Transition]):
        if not samples or any(s.actor_inputs is None for s in samples):
            raise ValueError("Missing structured actor inputs in PPO samples")
        return {key: torch.cat([s.actor_inputs[key] for s in samples], dim=0)
                for key in samples[0].actor_inputs}


class DependencyAwareTaskResourceActor(TaskResourceTransformerActor):
    """在任务注意力之前聚合直接后继特征，并显式提供下游任务信息。"""

    def __init__(self, *args, dependency_dim: int = 4, **kwargs):
        super().__init__(*args, **kwargs)
        hidden = self.task_embedding[0].out_features
        self.dependency_projection = nn.Linear(dependency_dim, hidden)
        self.message_mlp = nn.Sequential(
            nn.Linear(hidden * 2, hidden), nn.GELU(), nn.Linear(hidden, hidden)
        )
        self.message_norm = nn.LayerNorm(hidden)

    def _embed_task_nodes(self, tasks, structured, task_valid):
        if "dependency_features" not in structured or "dependency_matrix" not in structured:
            raise ValueError("Dependency-aware Actor requires dependency graph features")
        base = self.task_embedding(self.scaled_features(tasks))
        node = base + self.dependency_projection(structured["dependency_features"])
        valid = task_valid.float()
        adjacency = structured["dependency_matrix"] * valid.unsqueeze(-1) * valid.unsqueeze(-2)
        # 沿着前驱->后继的方向，将直接后继表示聚合到前驱节点；
        # 连续两次消息传播即可利用两跳下游信息。没有邻居的节点保持不变。
        for _ in range(2):
            degree = adjacency.sum(dim=-1, keepdim=True)
            message = torch.bmm(adjacency, node) / degree.clamp_min(1.0)
            update = self.message_mlp(torch.cat([node, message], dim=-1))
            node = self.message_norm(node + update * (degree > 0).float())
        return node


class DependencyAwareTransformerMAPPO(TransformerMAPPO):
    """第七阶段：任务图依赖增强的Transformer-MAPPO。"""

    def __init__(self, env: MultiAgentSchedulerEnv, *, hidden: int = 64,
                 heads: int = 4, layers: int = 2, **kwargs):
        if not env.include_dependency_features:
            raise ValueError("Set include_dependency_features=True in environment")
        super().__init__(env, hidden=hidden, heads=heads, layers=layers, **kwargs)
        example = env.observe()[env.agents[0]]
        self.actor = DependencyAwareTaskResourceActor(
            len(example["task_features"][0]),
            len(example["resource_features"][0]),
            len(example["match_features"][0][0]),
            env.max_tasks, env.max_resources_per_uav,
            hidden=hidden, heads=heads, layers=layers,
        )
        self.optimizer = torch.optim.Adam(
            list(self.actor.parameters()) + list(self.critic.parameters()),
            lr=kwargs.get("lr", 3e-4),
        )
        self.actor_kind = "dependency_transformer"
        self.architecture = {
            "hidden": hidden, "heads": heads, "layers": layers,
            "dependency_features": 4, "graph_message_steps": 2,
        }

    def select_actions(self, env, observations, *, greedy=False):
        if not env.include_dependency_features:
            raise ValueError("Dependency-aware Actor requires dependency observations")
        return super().select_actions(env, observations, greedy=greedy)


class CriticalPathTaskResourceActor(DependencyAwareTaskResourceActor):
    """第八阶段：在任务图消息传递结果中融合关键路径的时间预算。"""

    def __init__(self, *args, critical_dim: int = 6, **kwargs):
        super().__init__(*args, **kwargs)
        hidden = self.task_embedding[0].out_features
        self.critical_projection = nn.Sequential(
            nn.Linear(critical_dim, hidden), nn.Tanh(), nn.Linear(hidden, hidden),
        )
        self.critical_norm = nn.LayerNorm(hidden)

    def _embed_task_nodes(self, tasks, structured, task_valid):
        if "critical_path_features" not in structured:
            raise ValueError("Critical-path Actor requires critical-path features")
        base = super()._embed_task_nodes(tasks, structured, task_valid)
        extra = self.critical_projection(structured["critical_path_features"])
        return self.critical_norm(base + extra)


class CriticalPathTransformerMAPPO(DependencyAwareTransformerMAPPO):
    """基于关键路径时间裕量与任务依赖关系的共享Transformer策略。"""

    def __init__(self, env: MultiAgentSchedulerEnv, *, hidden: int = 64,
                 heads: int = 4, layers: int = 2, **kwargs):
        if not env.include_critical_path_features:
            raise ValueError("Set include_critical_path_features=True in environment")
        super().__init__(env, hidden=hidden, heads=heads, layers=layers, **kwargs)
        example = env.observe()[env.agents[0]]
        self.actor = CriticalPathTaskResourceActor(
            len(example["task_features"][0]),
            len(example["resource_features"][0]),
            len(example["match_features"][0][0]),
            env.max_tasks, env.max_resources_per_uav,
            hidden=hidden, heads=heads, layers=layers,
        )
        self.optimizer = torch.optim.Adam(
            list(self.actor.parameters()) + list(self.critic.parameters()),
            lr=kwargs.get("lr", 3e-4),
        )
        self.actor_kind = "critical_path_transformer"
        self.architecture = {
            "hidden": hidden, "heads": heads, "layers": layers,
            "dependency_features": 4, "critical_path_features": 6,
            "graph_message_steps": 2,
        }

    def select_actions(self, env, observations, *, greedy=False):
        if not env.include_critical_path_features:
            raise ValueError("Critical-path Actor requires critical-path observations")
        return super().select_actions(env, observations, greedy=greedy)
