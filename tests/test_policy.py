"""Structured planning, input validation and bundled model loading."""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

import pytest

from ubisched.experiments.integrated_scenario import build_integrated_case
from ubisched.integration.policy import ModelPolicy, StructuredAdapter
from ubisched.integration.snapshot import SnapshotError, make_live_env

ROOT = Path(__file__).resolve().parents[1]


def snapshot():
    tasks, resources, _ = build_integrated_case(13)
    return {"version": 2, "time": 0.0, "snapshot_id": "unit-test", "request_uav_id": "UAV1",
            "task_graph": asdict(tasks), "resource_graph": asdict(resources)}


def test_structured_matches_runtime_action_mask_without_mutating_snapshot():
    data = snapshot()
    before = deepcopy(data)
    adapter = StructuredAdapter(ModelPolicy("greedy_score"))
    out = adapter.decide(data)
    assert out["status"] == "ok" and out["note"].startswith("proposals_only")
    assert out["allocations"]
    env = make_live_env(data)
    observations = env.observe()
    for allocation in out["allocations"]:
        local = observations[allocation["uav_id"]]
        assert any(local["action_mask"][i] and label == (
            allocation["subtask_id"], allocation["resource_id"])
            for i, label in enumerate(local["action_labels"]) if label is not None)
    assert adapter.decide(data)["allocations"] == out["allocations"]
    assert data == before
    assert env.state.now == 0
    assert all(t.state not in ("finished", "running") for t in env.state.task_graph.subtasks)


def test_invalid_task_graph_rejected_before_planning():
    data = snapshot()
    data["task_graph"]["edges"].append({"src_subtask_id": "capture_0", "dst_subtask_id": "capture_0"})
    with pytest.raises(SnapshotError):
        StructuredAdapter(ModelPolicy("greedy_score")).decide(data)


def test_resource_and_request_owner_validated():
    data = snapshot()
    data["resource_graph"]["resources"][0]["owner_uav_id"] = ""
    with pytest.raises(SnapshotError):
        make_live_env(data)
    data = snapshot()
    data["request_uav_id"] = "nonexistent"
    with pytest.raises(SnapshotError):
        StructuredAdapter(ModelPolicy("greedy_score")).decide(data)


def test_completed_predecessor_identity_needed_for_data_transfer():
    data = snapshot()
    task = next(x for x in data["task_graph"]["subtasks"] if x["subtask_id"] == "capture_0")
    task["state"] = "finished"
    with pytest.raises(SnapshotError, match="missing completed assignment"):
        make_live_env(data)
    data["completed_assignments"] = [{"subtask_id": "capture_0", "resource_id": "cam_0", "end_time": 1.0}]
    data["time"] = 2.0
    env = make_live_env(data)
    assert env.state.get_subtask("infer_0").state == "ready"
    assert env.state.assignments[-1].resource_id == "cam_0"


@pytest.mark.parametrize("policy,filename", [
    ("mappo_mlp", "smoke_mappo_mlp_seed11.pt"),
    ("mappo_dependency_transformer", "smoke_dependency_transformer_seed11.pt"),
])
def test_bundled_model_checkpoint_inference(policy, filename):
    pytest.importorskip("torch")
    with pytest.warns(RuntimeWarning, match="smoke checkpoint"):
        adapter = StructuredAdapter(ModelPolicy(policy, ROOT / "models" / filename))
    out = adapter.decide(snapshot())
    assert out["policy"] == policy and out["allocations"]


def test_wrong_checkpoint_rejected():
    pytest.importorskip("torch")
    with pytest.raises(SnapshotError, match="model kind mismatch"):
        ModelPolicy("mappo_mlp", ROOT / "models/smoke_dependency_transformer_seed11.pt")
