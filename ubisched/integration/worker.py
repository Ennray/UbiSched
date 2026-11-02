"""本机执行适配器。资源绑定到配置里的程序，网络指令不能指定程序或 shell。

每条 command_id 只启动一次。进程中断后无法确认的指令保留待核对状态，
不能为了重试而再次启动可能仍在运行的物理任务。
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import logging
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import tempfile
import time

from ubisched.integration.client import RuntimeClient
from ubisched.integration.snapshot import identifier, number
from ubisched.integration.event_log import event, limited_event

LOG = logging.getLogger("ubisched.worker")


class ExecutionWorker:
    def __init__(self, client, uav_id, worker_id, executors, database, *, timeout=25):
        self.client = client
        self.uav_id = identifier(uav_id, "uav_id")
        self.worker_id = identifier(worker_id, "worker_id")
        self.executors = executors
        for resource_id, argv in executors.items():
            identifier(resource_id, "resource_id")
            if not isinstance(argv, list) or not argv or any(not isinstance(x, str) or not x for x in argv):
                raise ValueError("executor must be a nonempty argv list")
        self.timeout = number(timeout, "worker timeout", minimum=0.001)
        if str(database) != ":memory:":
            Path(database).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(database))
        self.db.execute("CREATE TABLE IF NOT EXISTS jobs (command_id TEXT PRIMARY KEY, state TEXT, result TEXT)")
        self.db.commit()

    @classmethod
    def from_file(cls, path):
        path = Path(path).resolve()
        config = json.loads(path.read_text(encoding="utf-8"))
        database = path.parent / config.get("database", "worker.sqlite3")
        return cls(RuntimeClient(config.get("url", "http://127.0.0.1:18767/v2/rpc")),
                   config["uav_id"], config["worker_id"], config["executors"], database,
                   timeout=config.get("timeout", 25))

    def close(self):
        self.db.close()

    def _report(self, command_id, result):
        response = self.client.call("feedback", request_id=f"finish-{command_id}", command_id=command_id,
                                   uav_id=self.uav_id, worker_id=self.worker_id, **result)
        event(LOG, "feedback_confirmed", "调度器已确认执行结果", command_id=command_id,
              result=result["result"], uav_id=self.uav_id, worker_id=self.worker_id)
        return response

    def run_once(self):
        response = self.client.call("poll_commands", uav_id=self.uav_id, worker_id=self.worker_id)
        if not response["commands"]:
            limited_event(LOG, "worker_wait", "连接正常，等待本无人机的指令", key=self.worker_id,
                          uav_id=self.uav_id, worker_id=self.worker_id)
        outcomes = []
        pending = []
        def persist_result(cid, result):
            self.db.execute("INSERT OR REPLACE INTO jobs VALUES (?, 'done', ?)",
                            (cid, json.dumps(result, allow_nan=False)))
            self.db.commit()
            outcomes.append(self._report(cid, result))
        for command in response["commands"]:
            cid = command["command_id"]
            event(LOG, "command_received", "收到指令", command_id=cid, uav_id=self.uav_id,
                  subtask_id=command.get("subtask_id"), resource_id=command.get("resource_id"),
                  operation=command.get("operation"), worker_id=self.worker_id)
            old = self.db.execute("SELECT state,result FROM jobs WHERE command_id=?", (cid,)).fetchone()
            if old:
                if old[0] == "done":
                    outcomes.append(self._report(cid, json.loads(old[1])))
                else:
                    limited_event(LOG, "recovery_required", "上次执行结果未知，不自动重跑", key=cid,
                                  level=logging.WARNING, command_id=cid, uav_id=self.uav_id)
                    outcomes.append({"command_id": cid, "status": "recovery_required",
                                     "reason": "previous execution outcome unknown; no automatic rerun"})
                continue
            if command["operation"] == "cancel":
                persist_result(cid, {"result": "cancelled"})
            elif command["resource_id"] not in self.executors:
                persist_result(cid, {"result": "failed", "detail": "no executor configured for resource"})
            else:
                self.db.execute("INSERT INTO jobs VALUES (?, 'started', NULL)", (cid,)); self.db.commit()
                self.client.call("feedback", request_id=f"start-{cid}", command_id=cid,
                                 uav_id=self.uav_id, worker_id=self.worker_id, result="running")
                pending.append(command)
        with ThreadPoolExecutor(max_workers=max(1, len(self.executors))) as pool:
            futures = {pool.submit(self._run_program, c): c["command_id"] for c in pending}
            for future in as_completed(futures):
                persist_result(futures[future], future.result())
        return outcomes

    def _run_program(self, command):
        started = time.monotonic()
        fields = {k: command.get(k) for k in ("command_id", "subtask_id", "resource_id", "uav_id")}
        event(LOG, "execution_started", "开始调用配置绑定的执行程序", **fields,
              argv=self.executors[command["resource_id"]])
        result = self._run_program_impl(command)
        event(LOG, "execution_finished", "本机执行程序已返回结果，等待反馈确认", **fields,
              level=logging.INFO if result["result"] == "completed" else logging.WARNING,
              elapsed_wall_s=round(time.monotonic()-started, 6), **result)
        return result

    def _run_program_impl(self, command):
        # Files prevent an executor's output from filling pipes or memory.
        with tempfile.TemporaryFile() as stdin, tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            stdin.write(json.dumps(command, ensure_ascii=False).encode()); stdin.seek(0)
            try:
                proc = subprocess.Popen(self.executors[command["resource_id"]], stdin=stdin,
                                        stdout=stdout, stderr=stderr, shell=False,
                                        start_new_session=(os.name == "posix"))
            except OSError as exc:
                return {"result": "failed", "detail": f"executor could not start: {exc}"[:1000]}
            try:
                proc.wait(timeout=min(self.timeout, max(0.001, command["deadline_at"]-command.get("delivery_time", command["created_at"]))))
            except subprocess.TimeoutExpired:
                if os.name == "posix":
                    os.killpg(proc.pid, signal.SIGKILL)
                else:
                    proc.kill()
                proc.wait()
                return {"result": "failed", "detail": "executor stopped after local timeout"}
            stdout.seek(0)
            stderr.seek(0)
            diagnostic = stderr.read(8193)
            if diagnostic:
                event(LOG, "executor_stderr", "执行程序诊断输出", command_id=command["command_id"],
                      text=diagnostic[:8192].decode("utf-8", errors="replace"), truncated=len(diagnostic)>8192)
            output = stdout.read(65537)
            if proc.returncode or len(output) > 65536:
                stderr.seek(0)
                detail = stderr.read(800).decode("utf-8", errors="replace")
                return {"result": "failed", "detail":
                        f"executor exit={proc.returncode}, output_limit={len(output)>65536}: {detail}"[:1000]}
            try:
                result = json.loads(output)
                if result.get("result") not in {"completed", "failed", "cancelled"}:
                    raise ValueError("executor must return a terminal result")
                fields = {"result": result["result"]}
                if "detail" in result:
                    if not isinstance(result["detail"], str) or len(result["detail"]) > 1000:
                        raise ValueError("invalid executor detail")
                    fields["detail"] = result["detail"]
                if "execution_energy_used" in result:
                    fields["execution_energy_used"] = number(result["execution_energy_used"], "execution_energy_used")
                if "outputs" in result:
                    outputs = result["outputs"]
                    if not isinstance(outputs, dict) or len(outputs) > 32 or any(
                            not isinstance(k, str) or not k or len(k) > 128 or
                            not isinstance(v, str) or not v or len(v) > 4096 for k, v in outputs.items()):
                        raise ValueError("invalid executor output references")
                    fields["outputs"] = outputs
                return fields
            except (ValueError, AttributeError, TypeError, UnicodeError):
                return {"result": "failed", "detail": "invalid executor JSON output"}

    def run_forever(self):
        event(LOG, "worker_started", "执行端启动，等待指令", uav_id=self.uav_id,
              worker_id=self.worker_id, resources=list(self.executors), url=self.client.url)
        try:
            while True:
                try:
                    self.run_once()
                except (ConnectionError, ValueError) as exc:
                    # Recorded jobs and pending results remain durable; never invent success.
                    limited_event(LOG, "worker_request_failed", "领取或反馈失败，将保留记录并重试",
                                  key=(self.worker_id, str(exc)), level=logging.WARNING,
                                  uav_id=self.uav_id, worker_id=self.worker_id, error=str(exc))
                time.sleep(0.2)
        except KeyboardInterrupt:
            event(LOG, "worker_stopped", "执行端停止", uav_id=self.uav_id, worker_id=self.worker_id)
