import copy
from dataclasses import asdict
import json
import socket
import threading
from pathlib import Path

import pytest

from ubisched.experiments.integrated_scenario import build_integrated_case
from ubisched.integration.structured_bridge import (
    ModelPolicy, SnapshotError, StructuredAdapter, StructuredBridgeServer,
    make_live_env,
)

ROOT = Path(__file__).resolve().parents[1]


def snapshot():
    t, r, _ = build_integrated_case(13)
    s = {"version": 2, "time": 0.0, "snapshot_id": "unit-test", "request_uav_id": "UAV1",
         "task_graph": asdict(t), "resource_graph": asdict(r)}
    for i, task in enumerate(s["task_graph"]["subtasks"]):
        task["legacy_task_index"] = i
    for i, resource in enumerate(s["resource_graph"]["resources"]):
        if resource["resource_type"] == "sensor":
            resource["legacy_sensor_index"] = i
    return s


def adapter(policy="greedy_score", filename=None):
    return StructuredAdapter(ModelPolicy(policy, ROOT / "models" / filename if filename else None))


def packet(s, prefix=b"UBI2|"):
    return prefix + json.dumps(s, ensure_ascii=False).encode("utf-8")


def test_structured_matches_runtime_action_mask():
    s = snapshot()
    out = adapter().decide(s)
    assert out["status"] == "ok" and out["note"].startswith("proposals_only")
    assert out["allocations"] and all(a["uav_id"] in ("UAV1", "UAV2", "UAV3") for a in out["allocations"])
    env = make_live_env(s)
    obs = env.observe()
    for alloc in out["allocations"]:
        assert any(obs[alloc["uav_id"]]["action_mask"][i] and label == (
            alloc["subtask_id"], alloc["resource_id"])
            for i, label in enumerate(obs[alloc["uav_id"]]["action_labels"]) if label is not None)
    # Online inference cannot advance the simulator or assume task completion.
    assert env.state.now == 0
    assert all(t.state not in ("finished", "running") for t in env.state.task_graph.subtasks)


def test_compact_compatibility_response():
    s = snapshot()
    a = adapter()
    wire = a.handle(b"UBI2C|UAV1|" + json.dumps(s).encode())
    assert wire.startswith(b"OK|")
    wrong = a.handle(b"UBI2C|UAV2|" + json.dumps(s).encode())
    assert wrong.startswith(b"ERR|")


def test_network_roundtrip_and_no_implicit_reservation():
    s = snapshot()
    a = adapter()
    with StructuredBridgeServer(("127.0.0.1", 0), a) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(2)
                for _ in range(2):
                    sock.sendto(packet(s), server.server_address)
                    data, _ = sock.recvfrom(64000)
                    reply = json.loads(data)
                    assert reply["allocations"] == a.decide(s)["allocations"]
        finally:
            server.shutdown()
            thread.join(timeout=2)


def test_bad_payloads_rejected():
    s = snapshot()
    cases = [b"UBI9|xxx", packet({}), b"UBI2|{broken", b"UBI2|"+b" "*48001]
    for raw in cases:
        assert adapter().handle(raw).startswith(b"ERR|")
    s["task_graph"]["edges"].append({"src_subtask_id": "capture_0", "dst_subtask_id": "capture_0"})
    assert adapter().handle(packet(s)).startswith(b"ERR|")


def test_task_order_and_resource_owner_bound():
    s = snapshot()
    s["resource_graph"]["resources"][0]["owner_uav_id"] = ""
    with pytest.raises(SnapshotError):
        make_live_env(s)
    s = snapshot()
    s["request_uav_id"] = "nonexistent"
    assert adapter().handle(packet(s)).startswith(b"ERR|")


def test_completed_predecessor_identity_needed_for_data_transfer():
    s = snapshot()
    t = next(x for x in s["task_graph"]["subtasks"] if x["subtask_id"] == "capture_0")
    t["state"] = "finished"
    with pytest.raises(SnapshotError, match="missing completed assignment"):
        make_live_env(s)
    s["completed_assignments"] = [{"subtask_id": "capture_0", "resource_id": "cam_0", "end_time": 1.0}]
    s["time"] = 2.0
    env = make_live_env(s)
    assert env.state.get_subtask("infer_0").state == "ready"
    assert env.state.assignments[-1].resource_id == "cam_0"


@pytest.mark.parametrize("policy,filename", [
    ("mappo_mlp", "stage11_mappo_mlp_seed11.pt"),
    ("mappo_dependency_transformer", "stage11_dependency_transformer_seed11.pt"),
])
def test_model_checkpoint_real_inference(policy, filename):
    s = snapshot()
    a = adapter(policy, filename)
    out = a.decide(s)
    assert out["policy"] == policy and out["allocations"]
    assert a.handle(b"UBI2C|UAV1|" + json.dumps(s).encode()).startswith(b"OK|")


def test_wrong_checkpoint_rejected():
    with pytest.raises(SnapshotError):
        adapter("mappo_mlp", "stage11_dependency_transformer_seed11.pt")
