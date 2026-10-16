from __future__ import annotations

"""教学与算法对比用的最小共享 Actor + 集中 Critic 的 MAPPO 基线。

- 所有 UAV 使用共享 MLP Actor，输入本机观测。
- Critic 使用全局状态输出团队价值，采用共享团队奖励。
- 采用 masked categorical 策略、PPO clip 更新和 GAE。
- on-policy 按完整回合采样；不实现并行环境、Transformer 或规模泛化。
"""

from dataclasses import dataclass
from typing import Callable, List, Dict

import torch
from torch import nn
from torch.distributions import Categorical

from ubisched.scheduling.multi_agent_env import MultiAgentSchedulerEnv


class MLP(nn.Module):
    def __init__(self, input_dim: int, output_dim: int, hidden: int = 128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden), nn.Tanh(),
            nn.Linear(hidden, hidden), nn.Tanh(),
            nn.Linear(hidden, output_dim),
        )

    def forward(self, data: torch.Tensor) -> torch.Tensor:
        return self.net(data)


@dataclass
class Transition:
    observations: torch.Tensor  # [N, local_dim]
    global_state: torch.Tensor  # [global_dim]
    masks: torch.Tensor  # [N, action_dim]
    actions: torch.Tensor  # [N]
    old_logprobs: torch.Tensor  # [N]
    old_value: float
    reward: float
    actor_inputs: Dict[str, torch.Tensor] | None = None


@dataclass
class Episode:
    transitions: List[Transition]
    bootstrap_value: float
    team_reward: float
    completion_rate: float
    conflicts: int
    status: str


class MAPPOBaseline:
    def __init__(
        self, env: MultiAgentSchedulerEnv, *, lr: float = 3e-4,
        gamma: float = 0.99, gae_lambda: float = 0.95,
        clip_ratio: float = 0.2, value_coef: float = 0.5,
        entropy_coef: float = 0.01, hidden: int = 128,
        coordinate_actions: bool = False,
        work_conserving: bool = False,
    ) -> None:
        observations, _ = env.reset()
        first = observations[env.agents[0]]
        self.actor = MLP(len(env.local_vector(first)), env.action_dim, hidden)
        self.critic = MLP(len(env.state_vector()), 1, hidden)
        self.optimizer = torch.optim.Adam(
            list(self.actor.parameters()) + list(self.critic.parameters()), lr=lr
        )
        self.gamma = gamma
        self.gae_lambda = gae_lambda
        self.clip_ratio = clip_ratio
        self.value_coef = value_coef
        self.entropy_coef = entropy_coef
        self.action_dim = env.action_dim
        self.coordinate_actions = coordinate_actions
        self.work_conserving = work_conserving
        self.deadline_features = env.include_deadline_features
        self._resources_per_uav = env.max_resources_per_uav
        self.agent_ids = env.agents
        self.max_tasks = env.max_tasks
        self.max_agents = env.max_agents

    def _make_actor_inputs(self, env: MultiAgentSchedulerEnv, observations):
        """扩展接口：基础MLP只使用扁平向量，结构化Actor可覆写。"""
        return None

    def _actor_logits(self, flat_inputs: torch.Tensor, actor_inputs=None):
        return self.actor(flat_inputs)

    def _batch_actor_inputs(self, samples: List[Transition]):
        return None

    def select_actions(self, env: MultiAgentSchedulerEnv, observations, *, greedy: bool = False):
        """生成联合动作及其精确的条件分布掩码，供训练和评估共用。

        coordinate_actions=True 时按 UAV 顺序采样；前一 UAV 选中的任务会
        从后一 UAV 的合法动作中剔除。PPO 更新仍使用采样时保存的掩码，
        保证 old/new log-prob 对应同一个条件策略。
        """
        if (env.action_dim != self.action_dim
            or env.max_resources_per_uav != self._resources_per_uav
            or env.include_deadline_features != self.deadline_features
            or env.max_tasks != self.max_tasks
            or env.max_agents != self.max_agents):
            raise ValueError("Incompatible multi-agent environment")
        inputs = torch.tensor(
            [env.local_vector(observations[agent]) for agent in env.agents],
            dtype=torch.float32,
        )
        masks = torch.tensor(
            [observations[agent]["action_mask"] for agent in env.agents],
            dtype=torch.bool,
        )
        actor_inputs = self._make_actor_inputs(env, observations)
        self._last_actor_inputs = actor_inputs
        with torch.no_grad():
            logits = self._actor_logits(inputs, actor_inputs)
            chosen = []
            log_probs = []
            claimed_task_slots = set()
            assigned = False
            # 保留前面 UAV 自主等待的可能，但最后一个有可行动作的 UAV
            # 如果此前都未领取任务，则必须领取一项任务，避免所有智能体无意义等待。
            eligible = [i for i in range(len(env.agents)) if bool(masks[i, :-1].any())]
            last_eligible = eligible[-1] if eligible else None
            for idx, _ in enumerate(env.agents):
                if self.coordinate_actions:
                    for task_slot in claimed_task_slots:
                        lo = task_slot * self._resources_per_uav
                        masks[idx, lo:lo + self._resources_per_uav] = False
                if (self.work_conserving and not assigned and idx == last_eligible
                    and bool(masks[idx, :-1].any())):
                    masks[idx, env.noop_index] = False
                if not masks[idx].any():
                    raise RuntimeError("At least the waiting action must be available")
                dist = Categorical(logits=logits[idx].masked_fill(~masks[idx], -1e9))
                action = (logits[idx].masked_fill(~masks[idx], -1e9).argmax()
                          if greedy else dist.sample())
                chosen.append(action)
                log_probs.append(dist.log_prob(action))
                if int(action.item()) != env.noop_index:
                    assigned = True
                    if self.coordinate_actions:
                        claimed_task_slots.add(int(action.item()) // self._resources_per_uav)
        return (inputs, masks, torch.stack(chosen), torch.stack(log_probs))

    def sample_episode(self, env: MultiAgentSchedulerEnv, *, greedy: bool = False) -> Episode:
        obs, _ = env.reset()
        trajectory: List[Transition] = []
        episode_return = 0.0
        info = {}
        while True:
            agent_inputs, masks, actions, old_logprobs = self.select_actions(
                env, obs, greedy=greedy
            )
            global_input = torch.tensor(env.state_vector(), dtype=torch.float32)
            with torch.no_grad():
                value = self.critic(global_input).item()
            joint_actions = {a: int(actions[i]) for i, a in enumerate(env.agents)}
            obs, reward, terminated, truncated, info = env.step(joint_actions)
            trajectory.append(Transition(
                observations=agent_inputs, global_state=global_input,
                masks=masks, actions=actions, old_logprobs=old_logprobs,
                old_value=value, reward=reward,
                actor_inputs=self._last_actor_inputs,
            ))
            episode_return += reward
            if terminated or truncated:
                break
        # 只有时间/步数截断才能 bootstrap；真正终止的价值为 0。
        with torch.no_grad():
            bootstrap_value = (
                self.critic(torch.tensor(env.state_vector(), dtype=torch.float32)).item()
                if truncated else 0.0
            )
        return Episode(
            transitions=trajectory, bootstrap_value=bootstrap_value,
            team_reward=episode_return,
            completion_rate=info["completion_rate"],
            conflicts=info["conflicts_total"], status=info["status"],
        )

    def update(self, episodes: List[Episode], *, epochs: int = 4) -> dict:
        if not episodes or epochs <= 0:
            raise ValueError("Need nonempty episodes and positive epochs")
        samples: List[Transition] = []
        advantage_list = []
        return_list = []
        for episode in episodes:
            transitions = episode.transitions
            advantages = [0.0] * len(transitions)
            gae = 0.0
            next_value = episode.bootstrap_value
            for t in reversed(range(len(transitions))):
                step = transitions[t]
                delta = step.reward + self.gamma * next_value - step.old_value
                gae = delta + self.gamma * self.gae_lambda * gae
                advantages[t] = gae
                next_value = step.old_value
            samples.extend(transitions)
            advantage_list.extend(advantages)
            return_list.extend(
                advantages[t] + transitions[t].old_value for t in range(len(transitions))
            )
        observations = torch.stack([x.observations for x in samples])  # [T,N,D]
        global_states = torch.stack([x.global_state for x in samples])
        action_masks = torch.stack([x.masks for x in samples])
        actions = torch.stack([x.actions for x in samples])
        old_logprobs = torch.stack([x.old_logprobs for x in samples])
        advantages = torch.tensor(advantage_list, dtype=torch.float32)
        returns = torch.tensor(return_list, dtype=torch.float32)
        if len(advantages) > 1:
            advantages = (advantages - advantages.mean()) / (advantages.std(unbiased=False) + 1e-8)
        metrics = {}
        batched_actor_inputs = self._batch_actor_inputs(samples)
        for _ in range(epochs):
            logits = self._actor_logits(observations, batched_actor_inputs).masked_fill(~action_masks, -1e9)
            distribution = Categorical(logits=logits)
            logprobs = distribution.log_prob(actions)
            ratios = (logprobs - old_logprobs).exp()
            adv = advantages.unsqueeze(-1).expand_as(ratios)
            surrogate = torch.minimum(
                ratios * adv,
                ratios.clamp(1.0 - self.clip_ratio, 1.0 + self.clip_ratio) * adv,
            )
            actor_loss = -surrogate.mean()
            values = self.critic(global_states).squeeze(-1)
            critic_loss = (values - returns).square().mean()
            entropy = distribution.entropy().mean()
            loss = actor_loss + self.value_coef * critic_loss - self.entropy_coef * entropy
            self.optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(
                list(self.actor.parameters()) + list(self.critic.parameters()), 0.5
            )
            self.optimizer.step()
            metrics = {
                "actor_loss": float(actor_loss.item()),
                "critic_loss": float(critic_loss.item()),
                "entropy": float(entropy.item()),
                "samples": len(samples),
            }
        return metrics

    def train(
        self, env_factory: Callable[[], MultiAgentSchedulerEnv], *,
        episodes: int = 32, episodes_per_update: int = 4, ppo_epochs: int = 4,
        report_interval: int = 8,
    ) -> List[dict]:
        if episodes <= 0 or episodes_per_update <= 0:
            raise ValueError("episodes and episodes_per_update must be positive")
        reports = []
        count = 0
        while count < episodes:
            batch = [
                self.sample_episode(env_factory())
                for _ in range(min(episodes_per_update, episodes - count))
            ]
            metrics = self.update(batch, epochs=ppo_epochs)
            count += len(batch)
            report = {
                "episodes": count,
                "reward_mean": sum(ep.team_reward for ep in batch) / len(batch),
                "completion_rate_mean": sum(ep.completion_rate for ep in batch) / len(batch),
                "conflicts_mean": sum(ep.conflicts for ep in batch) / len(batch),
                **metrics,
            }
            reports.append(report)
            if count % report_interval == 0 or count == episodes:
                print(
                    f"回合 {count:4d} | 平均奖励 {report['reward_mean']:+.3f} | "
                    f"完成率 {report['completion_rate_mean']:.0%} | "
                    f"冲突 {report['conflicts_mean']:.2f} | "
                    f"Critic误差 {report['critic_loss']:.4f}"
                )
        return reports
