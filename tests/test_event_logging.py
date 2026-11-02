"""Verify logs reflect committed outcomes and preserve the executor JSON protocol."""
import json
from pathlib import Path
import sys
import uuid

from ubisched.integration.event_log import configure_logging
from ubisched.integration.runtime import RuntimeCoordinator
from ubisched.integration.structured_bridge import ModelPolicy
from ubisched.integration.worker import ExecutionWorker
from tests.test_v2_runtime import snapshot


def records(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def request(runtime, operation, **kw):
    return runtime.handle({"operation": operation, "request_id": uuid.uuid4().hex, **kw})


def test_committed_command_correlates_and_replay_does_not_duplicate_log(tmp_path):
    _, log = configure_logging(tmp_path/"logs", "test")
    runtime = RuntimeCoordinator(ModelPolicy("greedy_score"), tmp_path/"db", clock=lambda: 0)
    try:
        request(runtime, "initialize", snapshot=snapshot())
        command = request(runtime, "schedule", at=0)["commands"][0]
        delivered = request(runtime, "poll_commands", uav_id="UAV1", worker_id="worker")["commands"][0]
        cid = delivered["command_id"]
        request(runtime, "feedback", command_id=cid, uav_id="UAV1", worker_id="worker", result="running")
        done = {"operation": "feedback", "request_id": "same-completion", "command_id": cid,
                "uav_id": "UAV1", "worker_id": "worker", "result": "completed", "at": 1}
        assert runtime.handle(done) == runtime.handle(done)
        events = [x for x in records(log) if x.get("command_id") == cid]
        assert [x["event"] for x in events] == ["assignment_committed", "command_dispatched", "command_running", "command_completed"]
        assert events[-1]["actual_end_time"] == 1
        assert events[0]["subtask_id"] == command["subtask_id"]
        assert events[0]["resource_id"] == command["resource_id"]
    finally:
        runtime.close()


def test_rejected_commit_never_logs_assignment_and_idle_is_limited(tmp_path):
    _, log = configure_logging(tmp_path/"logs", "test")
    runtime = RuntimeCoordinator(ModelPolicy("greedy_score"), ":memory:", clock=lambda: 0)
    try:
        for _ in range(5):
            assert request(runtime, "schedule")["status"] == "error"
        request(runtime, "initialize", snapshot=snapshot())
        result = request(runtime, "commit", expected_revision=0, plan_id="invalid")
        assert result["status"] == "error"
        events = records(log)
        assert sum(x["event"] == "waiting_initialize" for x in events) == 1
        assert any(x["event"] == "request_rejected" for x in events)
        assert not any(x["event"] == "assignment_committed" for x in events)
        assert request(runtime, "state")["commands"] == []
    finally:
        runtime.close()


def test_executor_stderr_does_not_break_stdout_json(tmp_path):
    _, log = configure_logging(tmp_path/"logs", "test")
    script = tmp_path/"exec.py"
    script.write_text('import json,sys\nprint("camera diagnostic",file=sys.stderr)\nprint(json.dumps({"result":"completed","outputs":{"image":"file:///image.png"}}))\n')
    worker = ExecutionWorker(None, "UAV1", "worker", {"cam": [sys.executable, str(script)]}, ":memory:")
    try:
        result = worker._run_program({"command_id": "cmd-test", "subtask_id": "capture", "uav_id": "UAV1",
                                      "resource_id": "cam", "created_at": 0, "deadline_at": 10})
        assert result["result"] == "completed"
        events = records(log)
        assert any(x["event"] == "executor_stderr" and "camera diagnostic" in x["text"] for x in events)
        assert any(x["event"] == "execution_finished" and x["elapsed_wall_s"] >= 0 for x in events)
    finally:
        worker.close()


def test_executor_failure_detail_is_preserved(tmp_path):
    configure_logging(tmp_path/"logs", "test")
    worker = ExecutionWorker(None, "UAV1", "worker", {"cam": [sys.executable, "-c",
        'print(\'{"result":"failed","detail":"camera unavailable"}\')']}, ":memory:")
    try:
        result = worker._run_program({"command_id": "cmd-failed", "resource_id": "cam", "created_at": 0, "deadline_at": 10})
        assert result == {"result": "failed", "detail": "camera unavailable"}
    finally:
        worker.close()
