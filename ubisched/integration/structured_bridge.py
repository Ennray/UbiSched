from __future__ import annotations

"""Stage 13 structured snapshot -> UbiSched policy -> allocation proposal.

The caller owns authoritative task/resource state. Inference NEVER advances simulated
clock, marks tasks complete or sends commands to AirSim. UBI2 returns JSON plans;
UBI2C returns one backward-compatible legacy sensor selection (when representable).
"""

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
import socketserver
from typing import Any

from ubisched.graph.match_matrix import RuleBasedScorer
from ubisched.graph.resource_graph import ResourceGraph
from ubisched.graph.task_graph import TaskGraph
from ubisched.scheduling.scheduling_state import AssignmentRecord, TransferReservation
from ubisched.scheduling.multi_agent_env import MultiAgentSchedulerEnv
from ubisched.experiments.evaluation import choose_rule_actions

MAX_PACKET = 48000
MODELS = {"mappo_mlp": "mappo_mlp", "mappo_dependency_transformer": "mappo_dependency_transformer"}
POLICIES = {"greedy_score", "earliest_deadline", *MODELS}
CAPACITIES = {"max_tasks": 8, "max_resources_per_uav": 3, "max_agents": 3}


class SnapshotError(ValueError):
    pass


def _finite_tree(value: Any, path: str = "root") -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise SnapshotError(f"non-string key: {path}")
            _finite_tree(v, f"{path}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            _finite_tree(v, f"{path}[{i}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise SnapshotError(f"non-finite number: {path}")


def _validate_graphs(task_graph: TaskGraph, resource_graph: ResourceGraph) -> None:
    tids = task_graph.subtask_ids()
    rids = resource_graph.resource_ids()
    if not tids or not rids or len(tids) != len(set(tids)) or len(rids) != len(set(rids)):
        raise SnapshotError("task/resource IDs must be nonempty and unique")
    if any(not t.subtask_id or t.state not in {"pending", "ready", "running", "finished", "failed"}
           or t.arrival_time < 0 or t.resource_count_min != 1 or t.resource_count_max != 1
           for t in task_graph.subtasks):
        raise SnapshotError("unsupported task state or multi-resource requirement")
    ids = set(tids)
    adj = {x: [] for x in tids}
    indeg = {x: 0 for x in tids}
    for e in task_graph.edges:
        if e.src_subtask_id not in ids or e.dst_subtask_id not in ids or e.src_subtask_id == e.dst_subtask_id:
            raise SnapshotError("edge references missing task or self-loop")
        adj[e.src_subtask_id].append(e.dst_subtask_id)
        indeg[e.dst_subtask_id] += 1
    queue = [t for t, count in indeg.items() if count == 0]
    visited = 0
    while queue:
        cur = queue.pop()
        visited += 1
        for nxt in adj[cur]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    if visited != len(tids):
        raise SnapshotError("task graph contains cycle")
    if any(not r.owner_uav_id for r in resource_graph.resources):
        raise SnapshotError("each resource needs owner_uav_id")


def make_live_env(snapshot: dict[str, Any]) -> MultiAgentSchedulerEnv:
    if not isinstance(snapshot, dict) or snapshot.get("version") != 2:
        raise SnapshotError("expected version=2 snapshot")
    if "task_graph" not in snapshot or "resource_graph" not in snapshot:
        raise SnapshotError("missing task_graph/resource_graph")
    _finite_tree(snapshot)
    tasks = TaskGraph.from_dict(snapshot["task_graph"])
    resources = ResourceGraph.from_dict(snapshot["resource_graph"])
    _validate_graphs(tasks, resources)
    now = snapshot.get("time", resources.timestamp)
    if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now) or now < 0:
        raise SnapshotError("invalid snapshot time")
    resources.timestamp = float(now)
    scorer = RuleBasedScorer({
        "strict_deadlines": False,
        "normalization": {"max_latency": 120.0, "max_energy": 1000.0,
                          "max_distance": 1000.0, "max_priority": 10.0,
                          "max_queue_length": 20.0, "max_cpu_frequency": 15.0},
    })
    env = MultiAgentSchedulerEnv(
        tasks, resources, scorer, max_tasks=CAPACITIES["max_tasks"],
        max_resources_per_uav=CAPACITIES["max_resources_per_uav"],
        max_agents=CAPACITIES["max_agents"], include_deadline_features=True,
        include_dependency_features=True,
    )
    env.reset()
    # A snapshot describes the current authoritative state. These records are
    # observations from the producer, not events synthesized by our simulator.
    state = env.state
    seen_finished = set()
    for rec in snapshot.get("completed_assignments", []):
        tid, rid = rec["subtask_id"], rec["resource_id"]
        task = state.get_subtask(tid)
        state.get_resource(rid)
        if task.state != "finished" or tid in seen_finished:
            raise SnapshotError("completed assignment inconsistent with finished task")
        seen_finished.add(tid)
        finish = float(rec.get("end_time", now))
        if not math.isfinite(finish) or finish > float(now) + 1e-8 or finish < 0:
            raise SnapshotError("bad completion timestamp")
        state.assignments.append(AssignmentRecord(tid, rid, finish, finish, 0.0, 0.0,
                                                   status="finished", actual_end_time=finish))
    # Existing link reservations must be supplied with observed dates by the
    # external producer. They are not reconstructed from task IDs.
    for rec in snapshot.get("transfer_reservations", []):
        reservation = TransferReservation(**rec)
        if reservation.start_time > reservation.end_time:
            raise SnapshotError("invalid transfer reservation time range")
        state.transfer_reservations.append(reservation)
    # A completed predecessor carrying data cannot be routed without the
    # source resource identity; return an error instead of fabricating it.
    for edge in tasks.edges:
        if edge.data_size_mb > 0 and state.get_subtask(edge.src_subtask_id).state == "finished":
            if edge.src_subtask_id not in seen_finished:
                raise SnapshotError("missing completed assignment for data predecessor")
    state.task_graph.update_ready_states(state.now)
    return env


@dataclass
class ModelPolicy:
    policy: str
    checkpoint: Path | None = None

    def __post_init__(self):
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
            self.hidden = int(self.weights["hidden"])
            self.heads = int(self.weights.get("heads", 4))
            self.layers = int(self.weights.get("layers", 1))
            torch.set_num_threads(1)
            self._cached_algo = None
            # Model initialization is done before the UDP server declares itself
            # ready, so the first C++ request is not lost to a cold start.
            from ubisched.experiments.integrated_scenario import make_integrated_env
            self._initialize_algo(make_integrated_env(13))
        else:
            self.weights = None

    def _initialize_algo(self, env: MultiAgentSchedulerEnv) -> None:
        from ubisched.algorithms.mappo_baseline import MAPPOBaseline
        from ubisched.algorithms.transformer_mappo import DependencyAwareTransformerMAPPO
        cls = MAPPOBaseline if self.policy == "mappo_mlp" else DependencyAwareTransformerMAPPO
        params = {"hidden": self.hidden, "coordinate_actions": True, "work_conserving": True}
        if cls is DependencyAwareTransformerMAPPO:
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
            rule = "greedy_score" if self.policy == "greedy_score" else "edf"
            return choose_rule_actions(env, observations, policy=rule)
        if (env.action_dim, len(env.local_vector(observations[env.agents[0]]))) != self._cached_dim:
            raise SnapshotError("incompatible online observation dimension")
        _, _, actions, _ = self._cached_algo.select_actions(env, observations, greedy=True)
        return {agent: int(actions[i]) for i, agent in enumerate(env.agents)}


class StructuredAdapter:
    def __init__(self, policy: ModelPolicy):
        self.policy = policy

    def decide(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        env = make_live_env(snapshot)
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
        except (SnapshotError, ValueError, KeyError, TypeError, UnicodeError, OverflowError) as exc:
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
