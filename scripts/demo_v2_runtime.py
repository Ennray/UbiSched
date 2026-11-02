"""在临时目录演示新版服务、执行端、反馈及任务依赖。全部是离线示例。"""
from pathlib import Path
import argparse
import json
import logging
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ubisched.integration.client import RuntimeClient
from ubisched.integration.runtime import RuntimeCoordinator
from ubisched.integration.runtime_server import RuntimeServer
from ubisched.integration.structured_bridge import ModelPolicy
from ubisched.integration.worker import ExecutionWorker
from ubisched.integration.event_log import configure_logging, event


def main():
    parser = argparse.ArgumentParser(description="带逐条日志的离线流程演示，执行端始终为 mock")
    parser.add_argument("--policy", default="greedy_score", choices=("greedy_score", "earliest_deadline",
                        "mappo_mlp", "mappo_transformer", "mappo_dependency_transformer", "mappo_critical_path_transformer"))
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--log-dir", type=Path)
    args = parser.parse_args()
    configure_logging(args.log_dir, "demo")
    checkpoint = args.checkpoint
    if checkpoint is None and args.policy == "mappo_dependency_transformer":
        checkpoint = ROOT/"models/stage11_dependency_transformer_seed11.pt"
    event(logging.getLogger("ubisched.demo"), "mock_demo_started", "离线模拟演示，不控制 AirSim，不验证算法效果",
          policy=args.policy, checkpoint=str(checkpoint) if checkpoint else None, executor="mock")
    with tempfile.TemporaryDirectory(prefix="ubisched_demo_") as folder:
        folder = Path(folder)
        # A fixed clock lets the example explicitly inject arrival events.
        runtime = RuntimeCoordinator(ModelPolicy(args.policy, checkpoint), folder/"runtime.db", clock=lambda: 0)
        with RuntimeServer(("127.0.0.1", 0), runtime) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            client = RuntimeClient(f"http://127.0.0.1:{server.server_port}/v2/rpc")
            snapshot = json.loads((ROOT/"configs/ubisched/structured_snapshot_example.json").read_text(encoding="utf-8"))
            workers = []
            try:
                client.call("initialize", snapshot=snapshot)
                owners = sorted({r["owner_uav_id"] for r in snapshot["resource_graph"]["resources"]})
                for owner in owners:
                    executors = {r["resource_id"]: [sys.executable, str(ROOT/"scripts/mock_executor.py")]
                                 for r in snapshot["resource_graph"]["resources"] if r["owner_uav_id"] == owner}
                    workers.append(ExecutionWorker(client, owner, f"demo-{owner}", executors, folder/f"{owner}.db"))
                for step in range(30):
                    state = client.call("state")
                    if state["summary"]["all_finished"]:
                        print(json.dumps({"offline_demo_only": True, **state["summary"],
                                          "commands": len(state["commands"])}, ensure_ascii=False, indent=2))
                        return 0
                    # Explicit artificial time, not a measured UAV duration.
                    client.call("telemetry", expected_revision=state["revision"],
                                at=max(state["snapshot"]["time"], step*0.25))
                    client.call("schedule")
                    for worker in workers:
                        worker.run_once()
                raise RuntimeError("offline demonstration did not finish")
            finally:
                for worker in workers:
                    worker.close()
                server.shutdown(); thread.join(); runtime.close()


if __name__ == "__main__":
    raise SystemExit(main())
