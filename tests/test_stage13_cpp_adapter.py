import json
import os
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from ubisched.integration.structured_bridge import ModelPolicy, StructuredAdapter, StructuredBridgeServer

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not shutil.which("g++"), reason="g++ unavailable")
def test_compiled_structured_client_calls_online_model(tmp_path):
    exe = tmp_path / "cpp_live_probe"
    subprocess.run(["g++", "-std=c++11", "-I", str(ROOT / "iSSROS" / "core"),
                    str(ROOT / "scripts" / "stage13_cpp_probe.cpp"), "-o", str(exe)],
                   check=True, capture_output=True)
    path = tmp_path / "snapshot.json"
    snapshot = json.loads((ROOT / "configs" / "ubisched" /
                           "structured_snapshot_example.json").read_text(encoding="utf-8"))
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    checkpoint = ROOT / "models" / "stage11_dependency_transformer_seed11.pt"
    with StructuredBridgeServer(("127.0.0.1", 0), StructuredAdapter(ModelPolicy(
        "mappo_dependency_transformer", checkpoint))) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        env = os.environ.copy()
        env["UBISCHED_STRUCTURED_PORT"] = str(server.server_address[1])
        try:
            assert subprocess.check_output([str(exe), str(path), "1111111"],
                                           env=env, text=True).strip() == "1|3|0"
            assert subprocess.check_output([str(exe), str(path), "1000000"],
                                           env=env, text=True).strip() == "3|-1|-1"
            snapshot["request_uav_id"] = "UAV2"
            path.write_text(json.dumps(snapshot), encoding="utf-8")
            assert subprocess.check_output([str(exe), str(path), "1111111"],
                                           env=env, text=True).strip() == "3|-1|-1"
        finally:
            server.shutdown()
            thread.join(timeout=2)
