"""Read-only AirSim monitor. Never arms, moves, pauses or resets any vehicle.

Run with the SAME Python environment as connectMARL.py, in another terminal.
Logs are saved beside this script under logs/airsim_monitor/.
"""
import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import time
import uuid


class Recorder:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.session = uuid.uuid4().hex
        self.text = (self.directory / "monitor.log").open("a", encoding="utf-8", buffering=1)
        self.json = (self.directory / "monitor.jsonl").open("a", encoding="utf-8", buffering=1)

    def record(self, name, message, **fields):
        row = {"time": datetime.now().astimezone().isoformat(timespec="milliseconds"),
               "wall_timestamp": time.time(), "session_id": self.session,
               "event": name, "message": message, **fields}
        encoded = json.dumps(row, ensure_ascii=False, allow_nan=False)
        self.json.write(encoded + "\n")
        self.text.write(f"{row['time']} [{name}] {message} " + json.dumps(fields, ensure_ascii=False, allow_nan=False) + "\n")
        if name != "rpc_started":
            print(f"{row['time']} [{name}] {message} " + json.dumps(fields, ensure_ascii=False, allow_nan=False), flush=True)

    def close(self):
        self.text.close()
        self.json.close()


def vector(value):
    if value is None:
        return None
    result = [float(value.x_val), float(value.y_val), float(value.z_val)]
    return result if all(math.isfinite(x) for x in result) else None


def state_fields(state, previous_timestamp):
    kin = state.kinematics_estimated
    stamp = int(getattr(state, "timestamp", 0))
    delta_ms = (stamp-previous_timestamp)/1e6 if stamp > 0 and previous_timestamp is not None else None
    landed = getattr(state, "landed_state", None)
    return {"position": vector(kin.position), "velocity": vector(getattr(kin, "linear_velocity", None)),
            "landed_state": int(landed) if landed is not None else None,
            "sim_timestamp_ns": stamp, "sim_time_step_ms": delta_ms}


def close_client(client):
    # AirSim wraps msgpackrpc.Client in the public `client` attribute.
    transport = getattr(client, "client", None)
    if transport is not None and callable(getattr(transport, "close", None)):
        try:
            transport.close()
        except Exception:
            pass


def run(api, args):
    recorder = Recorder(args.output)
    client = None
    previous = {}
    counts = {"iterations": 0, "failed_iterations": 0}
    start = time.monotonic()

    def call(name, fn, decode=lambda result: {"result": result}):
        recorder.record("rpc_started", "开始读取", operation=name)
        begin = time.monotonic()
        try:
            result = fn()
            fields = decode(result)
        except Exception as exc:
            recorder.record("rpc_error", "读取失败", operation=name,
                            elapsed_s=round(time.monotonic()-begin, 3), error_type=type(exc).__name__, error=str(exc))
            raise
        recorder.record("rpc_ok", "读取完成", operation=name,
                        elapsed_s=round(time.monotonic()-begin, 3), **fields)
        return result

    recorder.record("monitor_started", "开始状态监测，不发送任何飞行或仿真控制指令",
                    ip=args.ip, vehicles=args.vehicles, rpc_timeout_s=args.timeout,
                    interval_s=args.interval, duration_s=args.duration, log_dir=str(recorder.directory))
    try:
        while args.duration == 0 or time.monotonic()-start < args.duration:
            counts["iterations"] += 1
            tick = time.monotonic()
            try:
                if client is None:
                    client = api.MultirotorClient(ip=args.ip, timeout_value=args.timeout)
                result = call("ping", client.ping, lambda value: {"responding": bool(value)})
                if not result:
                    raise RuntimeError("AirSim ping 返回 False")
                # Official Python name is simIsPause; some wrappers use simIsPaused.
                paused_reader = getattr(client, "simIsPause", None)
                if not callable(paused_reader):
                    paused_reader = getattr(client, "simIsPaused", None)
                if callable(paused_reader):
                    call("read_pause_state", paused_reader, lambda value: {"paused": bool(value)})
                else:
                    recorder.record("pause_state_unavailable", "当前客户端没有暂停状态读取接口，继续读取位置")
                for uav in args.vehicles:
                    state = call(f"getMultirotorState:{uav}", lambda uav=uav: client.getMultirotorState(vehicle_name=uav),
                                 lambda value, uav=uav: state_fields(value, previous.get(uav)))
                    stamp = int(getattr(state, "timestamp", 0))
                    previous[uav] = stamp if stamp > 0 else None
                recorder.record("tick_finished", "本轮状态读取结束", iteration=counts["iterations"],
                                elapsed_s=round(time.monotonic()-tick, 3))
            except Exception as exc:
                counts["failed_iterations"] += 1
                recorder.record("tick_failed", "本轮读取失败，下轮重建监测连接后继续", iteration=counts["iterations"], error=str(exc))
                if client is not None:
                    close_client(client)
                client = None
            if args.once:
                break
            delay = args.interval - (time.monotonic()-tick)
            if args.duration:
                delay = min(delay, max(0, args.duration-(time.monotonic()-start)))
            if delay > 0:
                time.sleep(delay)
    except KeyboardInterrupt:
        recorder.record("monitor_interrupted", "用户结束监测，不改变 UE 或飞行状态")
    finally:
        if client is not None:
            close_client(client)
        recorder.record("monitor_finished", "监测结束；这些统计不代表任务完成", **counts)
        recorder.close()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="读取 AirSim 响应、暂停状态和两架 UAV 状态，不发送控制指令")
    parser.add_argument("--ip", default="127.0.0.1")
    parser.add_argument("--vehicles", nargs="+", default=["UAV1", "UAV2"])
    parser.add_argument("--timeout", type=float, default=2)
    parser.add_argument("--interval", type=float, default=2)
    parser.add_argument("--duration", type=float, default=900, help="监测秒数，默认 15 分钟，0 表示持续到 Ctrl+C")
    parser.add_argument("--once", action="store_true", help="仅读取一轮")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "logs" / "airsim_monitor")
    args = parser.parse_args(argv)
    if not all(math.isfinite(x) for x in (args.timeout, args.interval, args.duration)) or min(args.timeout, args.interval) <= 0 or args.duration < 0:
        parser.error("timeout、interval 必须为正数，duration 必须非负")
    try:
        import airsim
    except ImportError as exc:
        parser.error(f"请使用运行 connectMARL.py 的 AirSim Python 环境: {exc}")
    return run(airsim, args)


if __name__ == "__main__":
    raise SystemExit(main())
