"""启动真正的新版命令入口，检查自动调度与执行反馈。"""
from pathlib import Path
import signal
import json
import socket
import subprocess
import sys
import time

from ubisched.integration.client import RuntimeClient
from ubisched.integration.worker import ExecutionWorker

ROOT = Path(__file__).resolve().parents[1]


def test_cli_service_auto_schedules_and_stops(tmp_path):
    sample = json.loads((ROOT/"configs/ubisched/structured_snapshot_example.json").read_text())
    # Bind a temporary local port only for this subprocess test.
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
    log_path = tmp_path/"service.log"
    with log_path.open("w") as log:
        proc = subprocess.Popen([sys.executable,"-m","ubisched","serve","--policy","greedy_score",
                                 "--auto-schedule","--port",str(port),"--database",str(tmp_path/"state.db")],
                                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        client = RuntimeClient(f"http://127.0.0.1:{port}/v2/rpc", timeout=1, retries=0)
        workers = []
        try:
            deadline = time.monotonic()+10
            while True:
                try:
                    client.call("initialize", request_id="cli-init", snapshot=sample); break
                except ConnectionError:
                    assert proc.poll() is None, log_path.read_text()
                    assert time.monotonic() < deadline, log_path.read_text()
                    time.sleep(0.05)
            for owner in ("UAV1", "UAV2", "UAV3"):
                executors = {r["resource_id"]: [sys.executable,str(ROOT/"scripts/mock_executor.py")]
                             for r in sample["resource_graph"]["resources"] if r["owner_uav_id"] == owner}
                workers.append(ExecutionWorker(client,owner,f"cli-{owner}",executors,tmp_path/f"{owner}.db"))
            while True:
                state = client.call("state")
                if state["summary"]["all_finished"]:
                    break
                assert time.monotonic() < deadline, state
                for worker in workers:
                    worker.run_once()
                time.sleep(0.05)
            assert len(state["commands"]) == 6
            assert all(command["status"] == "completed" for command in state["commands"])
        finally:
            for worker in workers:
                worker.close()
            if proc.poll() is None:
                proc.send_signal(signal.SIGINT)
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill(); proc.wait()
        assert proc.returncode == 0, log_path.read_text()
