from __future__ import annotations

"""UbiSched to iS2ROS bridge (stage 12).

Protocol v1 is a constrained adapter for the *existing* iS2ROS observation:
    request: UBI1|<UAV integer id>|<weather_digit><task_0_flag>...<task_n_flag>
    reply:   OK|<zero-based task index>|<zero-based sensor index>
          | NONE
          | ERR|<reason>

This protocol deliberately cannot convey task DAGs, CPU resources, communication
reservations or completion acknowledgements; it must not be described as a full
physical execution-feedback integration. All sensor/task profiles are configurable.
"""

import argparse
import json
import math
import socketserver
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ubisched.graph.match_matrix import RuleBasedScorer
from ubisched.graph.resource_graph import ResourceGraph
from ubisched.graph.task_graph import TaskGraph
from ubisched.scheduling.assignment_executor import AssignmentExecutor
from ubisched.scheduling.rule_based_scheduler import RuleBasedScheduler
from ubisched.scheduling.scheduling_state import SchedulingState

MAX_DATAGRAM = 4096
MAX_LEGACY_TASKS = 48
SENSOR_IDS = (0, 1, 2)


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class Decision:
    task_index: int
    sensor_index: int
    score: float


class LegacyUbiSchedAdapter:
    """Maps legacy bit flags to a real UbiSched match matrix and rule scheduler.

    A fresh *snapshot* is evaluated for every request. The bridge does not infer
    task completion from bit transitions, and makes no persistent reservations.
    """

    def __init__(self, profile: dict[str, Any] | None = None):
        self.profile = profile or default_profile()
        self.scorer = RuleBasedScorer({
            "strict_deadlines": False,
            "normalization": {"max_latency": 120.0, "max_energy": 1000.0,
                              "max_distance": 1000.0, "max_priority": 10.0,
                              "max_queue_length": 20.0},
            "defaults": {"task_type_base_time": {"sense": 1.0}},
        })
        self.executor = AssignmentExecutor(self.scorer)
        self.scheduler = RuleBasedScheduler(self.executor)
        self._validate_profile()

    def _validate_profile(self):
        sensors = self.profile.get("sensors", [])
        if not isinstance(sensors, list) or not sensors:
            raise ProtocolError("profile requires non-empty sensors array")
        ids = [s.get("legacy_sensor_index") for s in sensors]
        if any(type(x) is not int or x not in SENSOR_IDS for x in ids) or len(ids) != len(set(ids)):
            raise ProtocolError("sensor index must be unique and one of 0,1,2")
        for sensor in sensors:
            quality = sensor.get("quality")
            if not isinstance(quality, (float, int)) or not math.isfinite(quality) or not 0 <= quality <= 1:
                raise ProtocolError("quality must be a finite value in [0,1]")
            if not isinstance(sensor.get("modality"), str) or not sensor["modality"]:
                raise ProtocolError("modality must be a non-empty string")
            for field in ("power", "remaining_energy"):
                v = sensor.get(field)
                if not isinstance(v, (float, int)) or not math.isfinite(v) or v < 0:
                    raise ProtocolError(f"{field} must be finite and nonnegative")

    @staticmethod
    def parse_request(raw: bytes) -> tuple[int, str]:
        if len(raw) > MAX_DATAGRAM:
            raise ProtocolError("request_too_long")
        try:
            text = raw.decode("ascii")
        except UnicodeDecodeError as exc:
            raise ProtocolError("non_ascii") from exc
        parts = text.split("|")
        if len(parts) != 3 or parts[0] != "UBI1":
            raise ProtocolError("bad_version_or_fields")
        uav, observation = parts[1], parts[2]
        if not uav.isascii() or not uav.isdecimal() or not 1 <= len(uav) <= 4:
            raise ProtocolError("invalid_uav")
        if not observation or len(observation) < 2 or len(observation) > MAX_LEGACY_TASKS + 1:
            raise ProtocolError("invalid_observation_length")
        if not observation.isascii() or not observation.isdecimal():
            raise ProtocolError("invalid_observation_digits")
        return int(uav), observation

    def decide(self, uav_id: int, observation: str) -> Decision | None:
        # This legacy input contains no DAG, deadline, network, position, CPU or
        # true live resource health. Attributes come only from the explicit profile.
        if not 1 <= uav_id <= 9999:
            raise ProtocolError("invalid_uav")
        if not observation.isascii() or not observation.isdecimal() or not 2 <= len(observation) <= MAX_LEGACY_TASKS+1:
            raise ProtocolError("invalid_observation_digits")
        tasks = []
        for i, flag in enumerate(observation[1:]):
            if flag == "0":
                continue
            tasks.append({
                "subtask_id": f"task_{i}", "task_type": "sense", "state": "ready",
                "priority": float(self.profile.get("priority_by_task", {}).get(str(i), 1.0)),
                "required_modalities_any": [str(self.profile.get("modality_by_task", {}).get(str(i), "legacy"))],
                "min_quality": float(self.profile.get("min_quality_by_task", {}).get(str(i), 0.0)),
                "deadline": 0, "max_latency": 1000,
            })
        if not tasks:
            return None
        resources = []
        for s in self.profile["sensors"]:
            resources.append({
                "resource_id": f"sensor_{s['legacy_sensor_index']}",
                "resource_type": "sensor", "owner_uav_id": f"UAV{uav_id}",
                "modalities": [s["modality"]],
                "sensing_quality": {s["modality"]: s["quality"]},
                "power": s["power"], "remaining_energy": s["remaining_energy"],
                "detection_range": 0, "online": bool(s.get("online", True)),
            })
        graph = TaskGraph.from_dict({"task_graph_id": f"legacy_uav_{uav_id}", "subtasks": tasks, "edges": []})
        resource_graph = ResourceGraph.from_dict({"resource_graph_id": f"legacy_resources_{uav_id}",
                                                  "resources": resources})
        state = SchedulingState(graph, resource_graph)
        choice = self.scheduler.select_assignment(self.executor.build_match_matrix(state))
        if choice is None:
            return None
        return Decision(int(choice.subtask_id.removeprefix("task_")),
                        int(choice.resource_id.removeprefix("sensor_")),
                        choice.match_score)

    def handle(self, request: bytes) -> bytes:
        try:
            uav_id, obs = self.parse_request(request)
            decision = self.decide(uav_id, obs)
            if decision is None:
                return b"NONE"
            return f"OK|{decision.task_index}|{decision.sensor_index}".encode("ascii")
        except ProtocolError as e:
            return f"ERR|{str(e)[:70]}".encode("ascii")
        except (ValueError, TypeError, KeyError) as e:
            return b"ERR|invalid_profile_or_snapshot"


def default_profile() -> dict[str, Any]:
    # Deliberately explicit demonstration values, not measured sensor quality.
    return {"sensors": [
        {"legacy_sensor_index": 0, "modality": "legacy", "quality": 0.85, "power": 1.0, "remaining_energy": 100},
        {"legacy_sensor_index": 1, "modality": "legacy", "quality": 0.80, "power": 1.0, "remaining_energy": 100},
        {"legacy_sensor_index": 2, "modality": "legacy", "quality": 0.75, "power": 1.0, "remaining_energy": 100},
    ]}


class _Handler(socketserver.BaseRequestHandler):
    def handle(self):
        data, sock = self.request
        reply = self.server.adapter.handle(data)
        sock.sendto(reply, self.client_address)


class BridgeServer(socketserver.UDPServer):
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], adapter: LegacyUbiSchedAdapter):
        super().__init__(address, _Handler)
        self.adapter = adapter


def main():
    parser = argparse.ArgumentParser(description="Legacy iS2ROS -> UbiSched rule-based compatibility bridge")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18765)
    parser.add_argument("--profile", type=Path, default=None)
    args = parser.parse_args()
    if not (1 <= args.port <= 65535):
        parser.error("port must be in 1..65535")
    profile = json.loads(args.profile.read_text(encoding="utf-8")) if args.profile else default_profile()
    adapter = LegacyUbiSchedAdapter(profile)
    with BridgeServer((args.host, args.port), adapter) as server:
        print(f"UbiSched bridge listening on {args.host}:{args.port} (legacy snapshot + rule policy)", flush=True)
        server.serve_forever(poll_interval=0.05)


if __name__ == "__main__":
    main()
