"""Old socket messages around the current graph policy. No HTTP/AirSim dependency.

This adapter preserves transport and wire bytes; missing state stays explicitly
profile-derived. Proposals sent over old sockets are NOT v2 execution commits.
"""
import argparse
import hashlib
import json
import logging
from pathlib import Path
import socket
import threading
import time

from ubisched.integration.event_log import configure_logging, event, limited_event
from ubisched.integration.structured_bridge import ModelPolicy, StructuredAdapter

LOG = logging.getLogger("ubisched.legacy_network")


def correlation_key(mode, observation, uav_id, task_index, sensor_index):
    raw = f"{mode}|{observation}|{uav_id}|{task_index}|{sensor_index}"
    return hashlib.sha256(raw.encode("ascii")).hexdigest()[:16]


def parse_observation(raw, task_count):
    text = raw.decode("ascii")
    if len(text) != task_count+1 or not text.isdecimal():
        raise ValueError(f"expected {task_count+1} ASCII digits")
    if any(x not in "01" for x in text[1:]):
        raise ValueError("task flags must be 0/1")
    return text


def extract_udp_observation(raw, task_count):
    text = raw.decode("ascii")
    parts = text.split("#")
    if len(parts) == 1:
        return parse_observation(raw, task_count), None
    if len(parts) != 6:
        raise ValueError("weather-only packet has no task state; no dispatch")
    # Keep weather as raw observations. No invented weather-to-quality mapping.
    weather = dict(zip(("time", "light", "fog", "rain", "dust"), parts[:5]))
    return parse_observation(parts[5].encode("ascii"), task_count), weather


def default_profile():
    return {"notice": "Configured demonstration attributes; not live sensor assessment.",
            "task_count": 5, "sensors": [
                {"legacy_sensor_index": 0, "modality": "rgb", "quality": 0.85, "power": 1.0, "remaining_energy": 100},
                {"legacy_sensor_index": 1, "modality": "infrared", "quality": 0.80, "power": 1.0, "remaining_energy": 100}],
            "priority_by_task": {}, "required_modalities_any": ["rgb", "infrared"]}


class LegacyGraphPolicy:
    def __init__(self, policy, profile):
        self.adapter = StructuredAdapter(policy)
        self.profile = profile
        self.task_count = profile["task_count"]
        if type(self.task_count) is not int or not 1 <= self.task_count <= 8:
            raise ValueError("current model supports 1..8 tasks")
        sensors = profile["sensors"]
        if not isinstance(sensors, list) or not 1 <= len(sensors) <= 3:
            raise ValueError("current model supports 1..3 sensors per UAV")
        ids = [s["legacy_sensor_index"] for s in sensors]
        if any(type(i) is not int or not 0 <= i <= 2 for i in ids) or len(ids) != len(set(ids)):
            raise ValueError("legacy sensor indices must be unique 0,1,2")
        if not profile.get("required_modalities_any"):
            raise ValueError("profile must declare required_modalities_any")

    def decide(self, observation, owners):
        parse_observation(observation.encode("ascii"), self.task_count)
        if not 1 <= len(owners) <= 3 or len(owners) != len(set(owners)):
            raise ValueError("expected 1..3 unique UAV owners")
        tasks = [{"subtask_id": f"task_{i}", "task_type": "sense", "state": "ready",
                  "priority": self.profile.get("priority_by_task", {}).get(str(i), 1.0),
                  "deadline": 0, "max_latency": 1000,
                  "required_modalities_any": self.profile["required_modalities_any"],
                  "min_quality": self.profile.get("min_quality_by_task", {}).get(str(i), 0.0)}
                 for i, flag in enumerate(observation[1:]) if flag == "1"]
        if not tasks:
            return []
        resources = [{"resource_id": f"{owner}_sensor_{s['legacy_sensor_index']}",
                      "resource_type": "sensor", "owner_uav_id": owner,
                      "modalities": [s["modality"]], "sensing_quality": {s["modality"]: s["quality"]},
                      "power": s["power"], "remaining_energy": s["remaining_energy"],
                      "online": s.get("online", True), "legacy_sensor_index": s["legacy_sensor_index"]}
                     for owner in owners for s in self.profile["sensors"]]
        snapshot = {"version": 2, "time": 0, "request_uav_id": owners[0],
                    "snapshot_id": "legacy-"+observation,
                    "task_graph": {"task_graph_id": "legacy_availability", "subtasks": tasks, "edges": []},
                    "resource_graph": {"resource_graph_id": "legacy_configured_sensors", "resources": resources}}
        proposal = self.adapter.decide(snapshot)
        by_resource = {r["resource_id"]: r["legacy_sensor_index"] for r in resources}
        return [{"uav_id": a["uav_id"], "task_index": int(a["subtask_id"][5:]),
                 "sensor_index": by_resource[a["resource_id"]], "match_score": a["score"]}
                for a in proposal["allocations"]]


class TcpSession:
    """Fixed 6-digit request / 4-digit reply by default. Never invent an idle code."""
    def __init__(self, policy, owners):
        if owners != ["UAV1", "UAV2"]:
            raise ValueError("uploaded old TCP script fixes its two positions to UAV1,UAV2")
        self.policy, self.owners = policy, owners
        self.previous = None

    def reply(self, observation):
        if self.previous:
            old, wire, choices = self.previous
            if observation == old:
                event(LOG, "legacy_reply_replayed", "重发相同旧请求的分配结果，不重复推理", observation=observation)
                return wire
            if observation[0] == old[0]:
                raise ValueError("task flags changed without old batch-completion marker; refusing ambiguous dispatch")
            expected = list(old[1:])
            for choice in choices:
                expected[choice["task_index"]] = "0"
            if list(observation[1:]) != expected:
                raise ValueError("unexpected task mask transition; reconnect cannot safely infer completion")
            event(LOG, "legacy_batch_reported", "收到旧协议的上一批完成标记，非逐条 v2 完成确认",
                  previous_observation=old, observation=observation,
                  tasks=[x["task_index"] for x in choices])
        if "1" not in observation[1:]:
            return None
        # Old TCP has no waiting-action encoding. Ask the same current policy
        # for each UAV in order, removing the first task before the next call.
        # No rule fallback or duplicate assignment is used to fill the reply.
        choices = []
        available = list(observation)
        for owner in self.owners:
            selected = self.policy.decide("".join(available), [owner])
            if len(selected) != 1:
                raise ValueError("old 4-digit TCP reply cannot express an idle UAV; no reply or duplicate task will be fabricated")
            choices.extend(selected)
            available[selected[0]["task_index"]+1] = "0"
        ordered = {c["uav_id"]: c for c in choices}
        if set(ordered) != set(self.owners):
            raise ValueError("old 4-digit TCP reply cannot express an idle UAV; no reply or duplicate task will be fabricated")
        choices = [ordered[owner] for owner in self.owners]
        wire = "".join(f"{c['task_index']}{c['sensor_index']}" for c in choices).encode("ascii")
        self.previous = observation, wire, choices
        return wire


def recv_exact(conn, size, stop):
    data = bytearray()
    while len(data) < size and not stop.is_set():
        try:
            chunk = conn.recv(size-len(data))
        except socket.timeout:
            continue
        if not chunk:
            raise EOFError("peer closed old TCP connection")
        data.extend(chunk)
    if stop.is_set():
        raise InterruptedError("stopped")
    return bytes(data)


def log_choices(mode, observation, choices, peer):
    for choice in choices:
        event(LOG, "legacy_assignment_sent", "旧格式分配已发送，不代表 AirSim 已执行完成",
              correlation_key=correlation_key(mode, observation, choice["uav_id"], choice["task_index"], choice["sensor_index"]),
              observation=observation, peer=str(peer), **choice)


def run_tcp(policy, pc_ip, port, owners, stop, connect_timeout=60):
    # Preserve the uploaded script's direction: PC listens, board actively connects.
    session = TcpSession(policy, owners)
    event(LOG, "legacy_tcp_connecting", "开发板连接电脑旧 TCP 服务", pc_ip=pc_ip, port=port)
    deadline = time.monotonic() + connect_timeout
    while True:
        if stop.is_set():
            raise InterruptedError("stopped before connection")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("旧 TCP 连接超时，请检查 AirSim 日志、监听地址及端口")
        try:
            conn = socket.create_connection((pc_ip, port), timeout=min(3, remaining))
            break
        except OSError:
            limited_event(LOG, "legacy_tcp_waiting", "等待电脑 AirSim 通过检查并监听旧 TCP 端口", interval=5, pc_ip=pc_ip, port=port)
            if stop.wait(min(0.5, max(0, deadline-time.monotonic()))):
                raise InterruptedError("stopped before connection")
    # Never reconnect automatically after dispatch: old bytes lack session identity.
    with conn:
        conn.settimeout(1)
        event(LOG, "legacy_tcp_connected", "旧 TCP 已连接", pc_ip=pc_ip, port=port)
        while not stop.is_set():
            observation = parse_observation(recv_exact(conn, policy.task_count+1, stop), policy.task_count)
            wire = session.reply(observation)
            if wire is None:
                event(LOG, "legacy_session_reported_finished", "电脑报告本次启用任务全部结束，旧 TCP 会话正常结束",
                      observation=observation)
                return
            conn.sendall(wire)
            event(LOG, "legacy_wire_reply", "已按原 TCP 格式发送四位分配", observation=observation, reply=wire.decode("ascii"))
            log_choices("tcp", observation, session.previous[2], (pc_ip, port))


def run_udp(policy, host, port, pc_ip, reply_port, owner, stop, cpp_bridge=False):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind((host, port)); sock.settimeout(1)
        event(LOG, "legacy_udp_ready", "旧 UDP 端口已监听", host=host, port=port, uav_id=owner,
              reply_peer="request_source" if cpp_bridge else f"{pc_ip}:{reply_port}", cpp_bridge=cpp_bridge)
        while not stop.is_set():
            try:
                data, peer = sock.recvfrom(4097)
            except socket.timeout:
                continue
            try:
                if len(data)>4096:
                    raise ValueError("oversize old message")
                if cpp_bridge:
                    parts = data.decode("ascii").split("|")
                    if len(parts)!=3 or parts[0]!="UBI1" or not parts[1].isascii() or not parts[1].isdecimal():
                        raise ValueError("expected UBI1|uav_id|observation")
                    if not 1<=int(parts[1])<=9999:
                        raise ValueError("legacy UAV ID must be 1..9999")
                    owner_for_request = "UAV"+str(int(parts[1]))
                    observation = parse_observation(parts[2].encode("ascii"), policy.task_count)
                else:
                    owner_for_request = owner
                    observation, weather = extract_udp_observation(data, policy.task_count)
                    if weather:
                        limited_event(LOG, "legacy_weather", "收到原天气字段，未自动换算传感器质量", key=owner, **weather)
                choices = policy.decide(observation, [owner_for_request])
                if not choices:
                    if cpp_bridge:
                        sock.sendto(b"NONE", peer)
                    limited_event(LOG, "legacy_no_assignment", "本次没有可下发动作，未发送伪造任务", key=(owner_for_request,observation))
                    continue
                choice = choices[0]
                wire = (f"OK|{choice['task_index']}|{choice['sensor_index']}" if cpp_bridge else
                        f"{choice['task_index']}#{choice['sensor_index']}#{owner_for_request}").encode("ascii")
                target = peer if cpp_bridge else (pc_ip, reply_port)
                sock.sendto(wire, target)
                log_choices("cpp-bridge" if cpp_bridge else "udp", observation, choices, target)
            except (ValueError, UnicodeError, KeyError) as exc:
                event(LOG, "legacy_packet_rejected", "旧消息未通过校验，不下发任务", level=logging.WARNING, peer=str(peer), error=str(exc))
                if cpp_bridge:
                    sock.sendto(b"ERR|invalid_legacy_message", peer)


def main(argv=None):
    parser = argparse.ArgumentParser(description="UbiSched current graph policy with unchanged old sockets")
    parser.add_argument("mode", choices=("tcp", "udp", "cpp-bridge"))
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--pc-ip", help="运行 UE/AirSim Python 的电脑 IP；同机验证可填 127.0.0.1")
    parser.add_argument("--port", type=int)
    parser.add_argument("--reply-port", type=int)
    parser.add_argument("--uav-id", type=int, default=1)
    parser.add_argument("--owners", default="UAV1,UAV2")
    parser.add_argument("--policy", default="mappo_dependency_transformer", choices=("greedy_score", "earliest_deadline", "mappo_mlp", "mappo_transformer", "mappo_dependency_transformer", "mappo_critical_path_transformer"))
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--log-dir", type=Path)
    parser.add_argument("--connect-timeout", type=float, default=60, help="仅在首次连接前等待电脑监听的秒数，断线后不自动重连")
    args = parser.parse_args(argv)
    if args.mode in {"tcp", "udp"} and not args.pc_ip:
        parser.error("this mode requires --pc-ip")
    if not 0 < args.connect_timeout <= 3600:
        parser.error("connect-timeout must be within (0,3600]")
    if not 1 <= args.uav_id <= 9999:
        parser.error("uav-id must be 1..9999")
    port = args.port if args.port is not None else {"tcp":65432,"udp":8887+args.uav_id,"cpp-bridge":18765}[args.mode]
    reply_port = args.reply_port if args.reply_port is not None else 9999-args.uav_id+1
    if not 1<=port<=65535 or args.mode=="udp" and not 1<=reply_port<=65535:
        parser.error("ports must be 1..65535")
    configure_logging(args.log_dir, f"legacy_{args.mode}_UAV{args.uav_id}")
    checkpoint = args.checkpoint
    if checkpoint is None and args.policy=="mappo_dependency_transformer":
        checkpoint = Path(__file__).resolve().parents[2]/"models/stage11_dependency_transformer_seed11.pt"
    profile = json.loads(args.profile.read_text(encoding="utf-8")) if args.profile else default_profile()
    policy = LegacyGraphPolicy(ModelPolicy(args.policy, checkpoint), profile)
    stop = threading.Event()
    event(LOG, "legacy_policy_ready", "当前图策略已加载，使用旧通信兼容模式，不使用 HTTP 18767",
          policy=args.policy, attributes="configured_profile", task_count=policy.task_count)
    try:
        if args.mode=="tcp":
            run_tcp(policy, args.pc_ip, port, args.owners.split(","), stop, args.connect_timeout)
        else:
            run_udp(policy, args.host, port, args.pc_ip, reply_port, f"UAV{args.uav_id}", stop, args.mode=="cpp-bridge")
    except KeyboardInterrupt:
        stop.set()
    except (OSError, ValueError, EOFError) as exc:
        event(LOG, "legacy_connection_stopped", "旧连接结束或不满足旧格式约束，未切换其他算法", level=logging.WARNING, error=str(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
