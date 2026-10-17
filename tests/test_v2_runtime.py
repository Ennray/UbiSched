"""新版运行协议的离线回归，不代表算法性能或 AirSim 验证。"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import sys
import threading

import pytest

from ubisched.experiments.integrated_scenario import make_integrated_env
from ubisched.integration.snapshot import SnapshotError, make_live_env
from ubisched.integration.structured_bridge import ModelPolicy, StructuredAdapter
from ubisched.integration.runtime import RuntimeCoordinator, state_snapshot
from ubisched.integration.runtime_server import RuntimeServer
from ubisched.integration.client import RuntimeClient
from ubisched.integration.worker import ExecutionWorker


def snapshot():
    return {"version": 2, "time": 0, "request_uav_id": "UAV1", "snapshot_id": "test",
            "task_graph": {"task_graph_id": "test", "subtasks": [
                {"subtask_id": "capture", "task_type": "sense", "required_modalities_any": ["rgb"],
                 "deadline": 10},
                {"subtask_id": "infer", "task_type": "classify", "compute_cycles": 2, "deadline": 10}],
                "edges": [{"src_subtask_id": "capture", "dst_subtask_id": "infer", "data_size_mb": 1}]},
            "resource_graph": {"resource_graph_id": "test", "resources": [
                {"resource_id": "cam", "resource_type": "sensor", "owner_uav_id": "UAV1",
                 "modalities": ["rgb"], "sensing_quality": {"rgb": 0.9}, "remaining_energy": 100, "power": 1},
                {"resource_id": "cpu", "resource_type": "compute", "owner_uav_id": "UAV2",
                 "cpu_frequency": 2, "remaining_energy": 100, "power": 1}],
                "communication_links": [{"source_uav_id": "UAV1", "target_uav_id": "UAV2", "bandwidth_mb_s": 2}]}}


@pytest.fixture
def runtime(tmp_path):
    service = RuntimeCoordinator(ModelPolicy("greedy_score"), tmp_path/"state.db", clock=lambda: 0,
                                 command_timeout=5)
    yield service
    service.close()


def call(runtime, op, **kw):
    import uuid
    return runtime.handle({"operation": op, "request_id": uuid.uuid4().hex, **kw})


def initialize(runtime):
    return call(runtime, "initialize", snapshot=snapshot())


def commit(runtime, *, request_id="commit"):
    state = call(runtime, "state")
    plan = call(runtime, "plan", expected_revision=state["revision"])
    assert plan["status"] == "ok", plan
    return runtime.handle({"operation": "commit", "request_id": request_id, "at": plan["plan"]["time"],
                           "expected_revision": state["revision"], "plan_id": plan["plan"]["plan_id"]})


def deliver(runtime, uav="UAV1", at=0):
    response = call(runtime, "poll_commands", uav_id=uav, worker_id="worker-"+uav, at=at)
    assert response["status"] == "ok", response
    return response["commands"]


def feedback(runtime, command, result, at=0, **kw):
    return call(runtime, "feedback", command_id=command["command_id"], uav_id=command["uav_id"],
                worker_id=command["worker_id"], result=result, at=at, **kw)


def test_training_and_online_features_match_after_reservations():
    train = make_integrated_env(13); train.reset()
    initial = {"version": 2, "time": 0, "task_graph": asdict(train.state.task_graph),
               "resource_graph": asdict(train.state.resource_graph)}
    online = make_live_env(initial)
    assert train.observe() == online.observe()
    train.executor.assign(train.state, "capture_0", "cam_0")
    wire = state_snapshot(train, initial)
    online = make_live_env(wire)
    assert train.observe() == online.observe()
    assert online.state.get_subtask("capture_0").state == "running"
    assert online.executor.scorer.estimate_execution(
        online.state.get_subtask("capture_1"), online.state.get_resource("cam_1")).latency == 1


@pytest.mark.parametrize("field,value", [("power", -1), ("power", True), ("remaining_energy", -1),
                                        ("occupied", "false"), ("cpu_frequency", float("nan"))])
def test_invalid_snapshot_values_rejected(field, value):
    sample = snapshot(); sample["resource_graph"]["resources"][0][field] = value
    with pytest.raises(SnapshotError):
        make_live_env(sample)


def test_deadline_policy_and_no_inference_side_effects():
    data = snapshot()
    result = StructuredAdapter(ModelPolicy("earliest_deadline")).decide(data)
    assert result["allocations"][0]["subtask_id"] == "capture"
    assert data["task_graph"]["subtasks"][0].get("state", "pending") == "pending"


def test_commit_reserves_once_and_feedback_unlocks_successor(runtime):
    initialize(runtime)
    response = commit(runtime); assert response["status"] == "ok", response
    assert len(response["commands"]) == 1
    state = call(runtime, "state")
    assert state["snapshot"]["task_graph"]["subtasks"][0]["state"] == "running"
    assert call(runtime, "plan", expected_revision=state["revision"])["plan"]["allocations"] == []
    command = deliver(runtime)[0]
    assert feedback(runtime, command, "running")["status"] == "ok"
    done = feedback(runtime, command, "completed", at=1, outputs={"image": "file:///frames/capture.png"})
    assert done["status"] == "ok", done
    next_result = commit(runtime, request_id="compute-commit")
    command2 = next_result["commands"][0]
    assert command2["resource_type"] == "compute" and command2["uav_id"] == "UAV2"
    assert command2["inputs"][0]["outputs"]["image"].endswith("capture.png")


def test_concurrent_commits_only_one_succeeds(runtime):
    initialize(runtime)
    plan = call(runtime, "plan", expected_revision=1)["plan"]
    def submit(i):
        return call(runtime, "commit", expected_revision=1, plan_id=plan["plan_id"], at=0)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(submit, range(2)))
    assert sorted(r["status"] for r in responses) == ["error", "ok"]
    assert len(call(runtime, "state")["commands"]) == 1


def test_idempotence_survives_restart_and_rejects_changed_payload(tmp_path):
    path = tmp_path/"persist.db"
    r = RuntimeCoordinator(ModelPolicy("greedy_score"), path, clock=lambda: 0)
    request = {"operation": "initialize", "request_id": "init", "snapshot": snapshot()}
    response = r.handle(request); commit_result = commit(r); r.close()
    r = RuntimeCoordinator(ModelPolicy("greedy_score"), path, clock=lambda: 0)
    try:
        assert r.handle(request) == response
        assert len(call(r, "state")["commands"]) == 1
        assert r.handle({**request, "snapshot": {}})["status"] == "error"
        assert call(r, "state")["commands"][0]["command_id"] == commit_result["commands"][0]["command_id"]
    finally:
        r.close()


def test_timeout_does_not_free_unconfirmed_execution(runtime):
    initialize(runtime); commit(runtime)
    command = deliver(runtime)[0]
    assert feedback(runtime, command, "running")["status"] == "ok"
    swept = call(runtime, "sweep", at=6)
    assert swept["cancelling"] == [command["command_id"]]
    state = call(runtime, "state")
    assert state["snapshot"]["resource_graph"]["resources"][0]["occupied"]
    assert state["snapshot"]["task_graph"]["subtasks"][0]["state"] == "running"
    assert call(runtime, "retry_task", expected_revision=state["revision"], subtask_id="capture", at=6)["status"] == "error"
    assert feedback(runtime, command, "cancelled", at=6)["status"] == "ok"
    state = call(runtime, "state")
    assert not state["snapshot"]["resource_graph"]["resources"][0]["occupied"]
    assert call(runtime, "retry_task", expected_revision=state["revision"], subtask_id="capture", at=6)["status"] == "ok"
    assert feedback(runtime, command, "completed", at=6)["status"] == "error"


def test_invalid_telemetry_rolls_back_and_feedback_owner_checked(runtime):
    initialize(runtime); commit(runtime)
    command = deliver(runtime)[0]; state = call(runtime, "state")
    result = call(runtime, "telemetry", expected_revision=state["revision"], at=0,
                  resources=[{"resource_id": "cam", "power": -1}])
    assert result["status"] == "error"
    assert call(runtime, "state")["snapshot"] == state["snapshot"]
    assert call(runtime, "feedback", command_id=command["command_id"], uav_id="UAV2",
                worker_id="worker-UAV1", result="completed", at=0)["status"] == "error"
    assert deliver(runtime, uav="UAV1", at=3)[0]["command_id"] == command["command_id"]
    assert call(runtime, "poll_commands", uav_id="UAV1", worker_id="other", at=3)["commands"] == []


def test_telemetry_offline_requires_confirmed_stop(runtime):
    initialize(runtime); commit(runtime)
    command = deliver(runtime)[0]; state = call(runtime, "state")
    updated = call(runtime, "telemetry", expected_revision=state["revision"], at=0,
                   resources=[{"resource_id": "cam", "online": False}])
    assert updated["status"] == "ok", updated
    state = call(runtime, "state")
    assert state["commands"][0]["status"] == "cancelling"
    assert state["snapshot"]["resource_graph"]["resources"][0]["occupied"]
    assert feedback(runtime, command, "cancelled")["status"] == "ok"


def test_http_worker_runs_local_program_and_deduplicates(tmp_path):
    runtime = RuntimeCoordinator(ModelPolicy("greedy_score"), tmp_path/"runtime.db")
    with RuntimeServer(("127.0.0.1", 0), runtime) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        client = RuntimeClient(f"http://127.0.0.1:{server.server_port}/v2/rpc")
        counter = tmp_path/"executions.txt"
        script = tmp_path/"executor.py"
        script.write_text("import json,sys\nfrom pathlib import Path\n"
                          "c=json.load(sys.stdin)\np=Path(sys.argv[1])\n"
                          "p.write_text(p.read_text()+'x' if p.exists() else 'x')\n"
                          "print(json.dumps({'result':'completed','outputs':{'data':'file:///test'}}))\n")
        worker = ExecutionWorker(client, "UAV1", "test-worker", {"cam": [sys.executable, str(script), str(counter)]},
                                 tmp_path/"worker.db")
        try:
            client.call("initialize", snapshot=snapshot())
            committed = commit(runtime)
            assert committed["status"] == "ok"
            worker.run_once(); worker.run_once()
            assert counter.read_text() == "x"
            assert client.call("state")["commands"][0]["status"] == "completed"
            with pytest.raises(ValueError):
                client.call("initialize", snapshot=snapshot())
        finally:
            worker.close(); server.shutdown(); thread.join(); runtime.close()


def test_checkpoint_contract_mismatch_is_rejected(tmp_path):
    torch = pytest.importorskip("torch")
    from ubisched.config import observation_contract, contract_hash
    from ubisched.algorithms.mappo_baseline import MAPPOBaseline
    env = make_integrated_env(11); algo = MAPPOBaseline(env, hidden=16)
    contract = observation_contract(); contract["scoring"]["normalization"]["max_latency"] = 999
    path = tmp_path/"wrong.pt"
    torch.save({"model":"mappo_mlp", "hidden":16, "actor":algo.actor.state_dict(),
                "observation_contract":contract, "contract_hash":contract_hash(contract)}, path)
    with pytest.raises(SnapshotError, match="contract mismatch"):
        ModelPolicy("mappo_mlp", path)


def test_schedule_tick_never_uses_estimated_finish_as_feedback(runtime):
    initialize(runtime)
    tick = call(runtime, "schedule", at=0)
    assert tick["commands"]
    tick = call(runtime, "schedule", at=20)
    assert tick["commands"] == []
    state = call(runtime, "state")
    assert state["commands"][0]["status"] == "cancelling"
    assert state["summary"]["running"] == 1 and state["summary"]["finished"] == 0


def test_assessment_mapping_and_new_task_capacity(runtime):
    initialize(runtime)
    result = call(runtime, "telemetry", expected_revision=1, at=0, assessments=[{
        "resource_id":"cam", "modality":"rgb", "metric":"recognition", "scores":[80, 72, 60]}])
    assert result["snapshot"]["resource_graph"]["resources"][0]["sensing_quality"]["rgb"] == 0.72
    rev = result["revision"]
    added = call(runtime, "add_tasks", expected_revision=rev, at=0, tasks=[{
        "task": {"subtask_id":"postprocess", "task_type":"classify", "compute_cycles":1},
        "predecessors":["infer"], "predecessor_data_sizes":{"infer":0.1}}])
    assert added["status"] == "ok", added
    state = call(runtime, "state")
    assert state["summary"]["total_tasks"] == 3
    assert state["snapshot"]["task_graph"]["subtasks"][-1]["state"] == "pending"


def test_worker_start_failure_and_uncertain_restart_never_reruns(tmp_path):
    worker = ExecutionWorker(None, "UAV1", "w", {"cam":[str(tmp_path/"missing-program")]}, tmp_path/"worker.db")
    command = {"command_id":"x", "resource_id":"cam", "created_at":0, "deadline_at":10}
    try:
        result = worker._run_program(command)
        assert result["result"] == "failed" and "could not start" in result["detail"]
        worker.db.execute("INSERT INTO jobs VALUES ('x','started',NULL)"); worker.db.commit()
        class Client:
            def call(self, operation, **kw):
                assert operation == "poll_commands"
                return {"commands":[command]}
        worker.client = Client()
        assert worker.run_once()[0]["status"] == "recovery_required"
    finally:
        worker.close()
