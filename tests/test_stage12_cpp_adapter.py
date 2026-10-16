"""Compiles and exercises the real C++ UDP client when a C++ compiler is available."""
import os
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from ubisched.integration.is2ros_bridge import BridgeServer, LegacyUbiSchedAdapter


@pytest.mark.skipif(not shutil.which("g++"), reason="g++ not installed on this platform")
def test_compiled_cpp_client_round_trip_and_fail_closed(tmp_path):
    root = Path(__file__).resolve().parents[1]
    binary = tmp_path / "cpp_probe"
    subprocess.run(["g++", "-std=c++11", "-I", str(root / "iSSROS" / "core"),
                    str(root / "scripts" / "stage12_cpp_probe.cpp"), "-o", str(binary)],
                   check=True, capture_output=True)
    with BridgeServer(("127.0.0.1", 0), LegacyUbiSchedAdapter()) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        env = os.environ.copy()
        env.update(UBISCHED_BRIDGE_ENABLE="1", UBISCHED_BRIDGE_HOST="127.0.0.1",
                   UBISCHED_BRIDGE_PORT=str(server.server_address[1]))
        try:
            out = subprocess.check_output([str(binary), "110"], env=env, text=True).strip()
            assert out == "1|0|0"  # ASSIGNED and a legal legacy index pair
            assert subprocess.check_output([str(binary), "100"], env=env, text=True).strip() == "2|-1|-1"
            assert subprocess.check_output([str(binary), "x10"], env=env, text=True).strip() == "3|-1|-1"
        finally:
            server.shutdown()
            thread.join(timeout=2)
    env["UBISCHED_BRIDGE_ENABLE"] = "0"
    assert subprocess.check_output([str(binary), "110"], env=env, text=True).strip() == "0|-1|-1"
