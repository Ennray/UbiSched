"""模型加载、规则选择及基于结构化快照的分配建议。"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import warnings
from pathlib import Path
from typing import Any

from ubisched.config import observation_contract, contract_hash
from ubisched.integration.snapshot import SnapshotError, make_live_env
from ubisched.scheduling.multi_agent_env import MultiAgentSchedulerEnv
from ubisched.experiments.evaluation import choose_rule_actions

MODELS = {name: name for name in ("mappo_mlp", "mappo_transformer",
          "mappo_dependency_transformer", "mappo_critical_path_transformer")}
POLICIES = {"greedy_score", "earliest_deadline", *MODELS}
# Only these bundled interface-check weights have a known training profile.
BUNDLED_SMOKE_HASHES = {
    "85c13f34ca10ea6519bfad16b9ff36d327920512c597f0526e30b8009d427428",
    "28e4c0fbee35bba93956eeab79ce0770e6929428c0e2f45215053ca3756cfa87",
}


@dataclass
class ModelPolicy:
    policy: str
    checkpoint: Path | None = None

    def __post_init__(self):
        self.critical_path = self.policy == "mappo_critical_path_transformer"
        self.contract = observation_contract(critical_path=self.critical_path)
        if self.policy not in POLICIES:
            raise SnapshotError("unknown policy")
        if self.policy in MODELS:
            if self.checkpoint is None or not self.checkpoint.is_file():
                raise SnapshotError("selected model requires existing --checkpoint")
            import torch
            # Never deserialize arbitrary Python objects from model files.
            self.weights = torch.load(self.checkpoint, map_location="cpu", weights_only=True)
            if self.weights.get("model") != self.policy:
                raise SnapshotError("checkpoint model kind mismatch")
            saved = self.weights.get("observation_contract")
            if saved is None:
                digest = hashlib.sha256(self.checkpoint.read_bytes()).hexdigest()
                if digest not in BUNDLED_SMOKE_HASHES:
                    raise SnapshotError("checkpoint lacks observation_contract; retrain with current entry")
                warnings.warn("Bundled smoke checkpoint: using its documented training profile; not a validated model", RuntimeWarning)
            elif saved != self.contract or self.weights.get("contract_hash") != contract_hash(saved):
                raise SnapshotError("checkpoint observation contract mismatch")
            self.hidden = int(self.weights["hidden"])
            self.heads = int(self.weights.get("heads", 4))
            self.layers = int(self.weights.get("layers", 1))
            torch.set_num_threads(1)
            self._cached_algo = None
            # Initialize and warm the model before accepting runtime requests.
            # Warm with a minimal schema example, independent of experiment generators.
            sample = {"version": 2, "time": 0,
                      "task_graph": {"task_graph_id": "warm", "subtasks": [
                          {"subtask_id": "warm", "task_type": "sense", "required_modalities_any": ["rgb"]}]},
                      "resource_graph": {"resource_graph_id": "warm", "resources": [
                          {"resource_id": "warm", "resource_type": "sensor", "owner_uav_id": "UAV1",
                           "modalities": ["rgb"], "remaining_energy": 100}]}}
            self._initialize_algo(make_live_env(sample, critical_path=self.critical_path))
        else:
            self.weights = None

    def _initialize_algo(self, env: MultiAgentSchedulerEnv) -> None:
        from ubisched.algorithms.mappo_baseline import MAPPOBaseline
        from ubisched.algorithms.transformer_mappo import (
            TransformerMAPPO, DependencyAwareTransformerMAPPO, CriticalPathTransformerMAPPO)
        cls = {"mappo_mlp": MAPPOBaseline, "mappo_transformer": TransformerMAPPO,
               "mappo_dependency_transformer": DependencyAwareTransformerMAPPO,
               "mappo_critical_path_transformer": CriticalPathTransformerMAPPO}[self.policy]
        params = {"hidden": self.hidden, "coordinate_actions": True, "work_conserving": True}
        if cls is not MAPPOBaseline:
            params.update(heads=self.heads, layers=self.layers)
        algo = cls(env, **params)
        try:
            algo.actor.load_state_dict(self.weights["actor"], strict=True)
        except RuntimeError as exc:
            raise SnapshotError("checkpoint does not match observation schema") from exc
        algo.actor.eval()
        self._cached_algo = algo
        self._cached_dim = (env.action_dim, len(env.local_vector(env.observe()[env.agents[0]])))
        # Warm the inference machinery once, not on the first network request.
        algo.select_actions(env, env.observe(), greedy=True)

    def choose(self, env: MultiAgentSchedulerEnv, observations) -> dict[str, int]:
        if self.weights is None:
            rule = "greedy_score" if self.policy == "greedy_score" else "earliest_deadline"
            return choose_rule_actions(env, observations, policy=rule)
        if (env.action_dim, len(env.local_vector(observations[env.agents[0]]))) != self._cached_dim:
            raise SnapshotError("incompatible online observation dimension")
        _, _, actions, _ = self._cached_algo.select_actions(env, observations, greedy=True)
        return {agent: int(actions[i]) for i, agent in enumerate(env.agents)}


class StructuredAdapter:
    def __init__(self, policy: ModelPolicy):
        self.policy = policy

    def decide(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        env = make_live_env(snapshot, critical_path=self.policy.critical_path)
        request_uav = snapshot.get("request_uav_id")
        if not isinstance(request_uav, str) or request_uav not in env.agents:
            raise SnapshotError("request_uav_id not found in resource owners")
        obs = env.observe()
        actions = self.policy.choose(env, obs)
        accepted: list[dict[str, Any]] = []
        claimed: set[str] = set()
        for agent in env.agents:
            action = actions[agent]
            local = obs[agent]
            if action == env.noop_index:
                continue
            if not isinstance(action, int) or not 0 <= action < env.noop_index or not local["action_mask"][action]:
                raise SnapshotError("policy returned masked action")
            label = local["action_labels"][action]
            if label is None or label[0] in claimed:
                raise SnapshotError("duplicate task allocation")
            claimed.add(label[0])
            entry = env.executor.score_assignment(env.state, *label)
            if not entry.feasible:
                raise SnapshotError("policy returned infeasible task/resource")
            # Reserve only in this disposable planning copy. This verifies joint
            # energy/link constraints without changing the caller's snapshot.
            env.executor.assign(env.state, *label)
            accepted.append({"uav_id": agent, "subtask_id": label[0], "resource_id": label[1],
                             "score": round(entry.match_score, 6)})
        result = {"version": 2, "status": "ok", "policy": self.policy.policy,
                  "request_uav_id": request_uav, "snapshot_id": snapshot.get("snapshot_id"),
                  "time": env.state.now, "allocations": accepted,
                  "note": "proposals_only_no_reservation_or_dispatch"}
        return result
