from __future__ import annotations

"""Stage 13 structured snapshot -> UbiSched policy -> allocation proposal.

The caller owns authoritative task/resource state. Inference NEVER advances simulated
clock, marks tasks complete or sends commands to AirSim. UBI2 returns JSON plans;
UBI2C returns one backward-compatible legacy sensor selection (when representable).
"""

import argparse
from dataclasses import dataclass
import json
import hashlib
import warnings
from pathlib import Path
import socketserver
from typing import Any

from ubisched.config import CAPACITIES, observation_contract, contract_hash
from ubisched.integration.snapshot import SnapshotError, make_live_env
from ubisched.graph.resource_graph import ResourceGraph
from ubisched.graph.task_graph import TaskGraph
from ubisched.scheduling.scheduling_state import AssignmentRecord, TransferReservation
from ubisched.scheduling.multi_agent_env import MultiAgentSchedulerEnv
from ubisched.experiments.evaluation import choose_rule_actions

MAX_PACKET = 48000
MODELS = {name: name for name in ("mappo_mlp", "mappo_transformer",
          "mappo_dependency_transformer", "mappo_critical_path_transformer")}
POLICIES = {"greedy_score", "earliest_deadline", *MODELS}
# Only these bundled Stage 11 files have a known historical training profile.
BUNDLED_LEGACY_HASHES = {
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
                if digest not in BUNDLED_LEGACY_HASHES:
                    raise SnapshotError("checkpoint lacks observation_contract; retrain with current entry")
                warnings.warn("Bundled Stage 11 smoke checkpoint: using its documented training profile; not a validated model", RuntimeWarning)
            elif saved != self.contract or self.weights.get("contract_hash") != contract_hash(saved):
                raise SnapshotError("checkpoint observation contract mismatch")
            self.hidden = int(self.weights["hidden"])
            self.heads = int(self.weights.get("heads", 4))
            self.layers = int(self.weights.get("layers", 1))
            torch.set_num_threads(1)
            self._cached_algo = None
            # Model initialization is done before the UDP server declares itself
            # ready, so the first C++ request is not lost to a cold start.
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

    @staticmethod
    def to_legacy_reply(snapshot: dict[str, Any], result: dict[str, Any]) -> bytes:
        owner = result["request_uav_id"]
        mine = [a for a in result["allocations"] if a["uav_id"] == owner]
        if not mine:
            return b"NONE"
        task = next((x for x in snapshot["task_graph"]["subtasks"]
                     if x["subtask_id"] == mine[0]["subtask_id"]), None)
        resource = next((x for x in snapshot["resource_graph"]["resources"]
                         if x["resource_id"] == mine[0]["resource_id"]), None)
        if task is None or resource is None or resource["resource_type"] != "sensor":
            return b"ERR|legacy_dispatch_not_supported"
        ti, si = task.get("legacy_task_index"), resource.get("legacy_sensor_index")
        if type(ti) is not int or not 0 <= ti <= 47 or type(si) is not int or not 0 <= si <= 2:
            return b"ERR|legacy_index_mapping_missing"
        return f"OK|{ti}|{si}".encode("ascii")

    def handle(self, packet: bytes) -> bytes:
        try:
            if len(packet) > MAX_PACKET:
                raise SnapshotError("packet_too_large")
            if packet.startswith(b"UBI2|"):
                snapshot = json.loads(packet[5:].decode("utf-8"))
                result = self.decide(snapshot)
                return json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
            if packet.startswith(b"UBI2C|"):
                parts = packet.split(b"|", 2)
                if len(parts) != 3 or not parts[1].startswith(b"UAV"):
                    raise SnapshotError("bad_compat_request")
                sender = parts[1].decode("ascii")
                snapshot = json.loads(parts[2].decode("utf-8"))
                if snapshot.get("request_uav_id") != sender:
                    raise SnapshotError("request owner mismatch")
                result = self.decide(snapshot)
                return self.to_legacy_reply(snapshot, result)
            raise SnapshotError("bad_version")
        except (SnapshotError, ValueError, KeyError, TypeError, UnicodeError, OverflowError, RecursionError) as exc:
            return f"ERR|{type(exc).__name__}:{str(exc)[:90]}".encode("ascii", errors="replace")


class _Handler(socketserver.BaseRequestHandler):
    def handle(self):
        packet, sock = self.request
        sock.sendto(self.server.adapter.handle(packet), self.client_address)


class StructuredBridgeServer(socketserver.UDPServer):
    allow_reuse_address = True
    max_packet_size = MAX_PACKET + 1024

    def __init__(self, address, adapter: StructuredAdapter):
        super().__init__(address, _Handler)
        self.adapter = adapter


def main(argv=None):
    p = argparse.ArgumentParser(description="UbiSched structured online inference (not AirSim execution)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=18766)
    p.add_argument("--policy", choices=sorted(POLICIES), default="greedy_score")
    p.add_argument("--checkpoint", type=Path)
    args = p.parse_args(argv)
    if not 1 <= args.port <= 65535:
        p.error("bad port")
    adapter = StructuredAdapter(ModelPolicy(args.policy, args.checkpoint))
    with StructuredBridgeServer((args.host, args.port), adapter) as server:
        print(f"UbiSched UBI2 ready {args.host}:{args.port} policy={args.policy}", flush=True)
        server.serve_forever(poll_interval=0.05)


if __name__ == "__main__":
    main()
