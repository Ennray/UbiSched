"""在临时目录演示新版服务、执行端、反馈及任务依赖。全部是离线示例。"""
from pathlib import Path
import json
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


def main():
    with tempfile.TemporaryDirectory(prefix="ubisched_demo_") as folder:
        folder = Path(folder)
        # A fixed clock lets the example explicitly inject arrival events.
        runtime = RuntimeCoordinator(ModelPolicy("greedy_score"), folder/"runtime.db", clock=lambda: 0)
        with RuntimeServer(("127.0.0.1", 0), runtime) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            client = RuntimeClient(f"http://127.0.0.1:{server.server_port}/v2/rpc")
            snapshot = json.loads((ROOT/"configs/ubisched/structured_snapshot_example.json").read_text())
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
