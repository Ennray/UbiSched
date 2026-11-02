"""新版有状态运行核心。提交、指令、反馈、请求去重在同一个数据库事务中保存。

运行时只根据外部反馈完成任务。估计结束时间仅供决策使用，不能代替反馈。
"""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time
import uuid

from ubisched.config import contract_hash
from ubisched.graph.task_graph import SubTask
from ubisched.integration.snapshot import SnapshotError, identifier, number, finite_tree, make_live_env
from ubisched.integration.structured_bridge import StructuredAdapter
from ubisched.integration.telemetry import assessment_patch

ACTIVE = {"queued", "dispatched", "accepted", "running", "cancelling"}
FINAL = {"completed", "failed", "cancelled"}


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True)


def state_snapshot(env, previous):
    """保留旧编号映射，但不以旧编号作为新版任务和资源身份。"""
    state = env.state
    result = {"version": 2, "time": state.now, "snapshot_id": previous.get("snapshot_id"),
              "request_uav_id": previous.get("request_uav_id", env.agents[0]),
              "energy_normalization": env._base._resource_energy_scale,
              "task_graph": asdict(state.task_graph), "resource_graph": asdict(state.resource_graph),
              "completed_assignments": [], "running_assignments": [],
              "transfer_reservations": [asdict(x) for x in state.transfer_reservations]}
    for group, key, field in (("subtasks", "task_graph", "subtask_id"),
                              ("resources", "resource_graph", "resource_id")):
        old = {x[field]: x for x in previous[key][group]}
        for item in result[key][group]:
            for name in ("legacy_task_index", "legacy_sensor_index"):
                if name in old.get(item[field], {}):
                    item[name] = old[item[field]][name]
    for a in state.assignments:
        if a.status == "finished":
            result["completed_assignments"].append({"subtask_id": a.subtask_id,
                "resource_id": a.resource_id, "end_time": a.actual_end_time})
        elif a.status == "running":
            result["running_assignments"].append({"subtask_id": a.subtask_id,
                "resource_id": a.resource_id, "start_time": a.start_time,
                "completion_time": a.completion_time, "estimated_energy": a.estimated_energy})
    return result


class RuntimeCoordinator:
    """一个任务集合由一个协调器管理。可恢复存储不等于分布式共识。"""

    def __init__(self, policy, database, *, command_timeout=30.0, retry_interval=2.0, clock=time.time):
        self.adapter = StructuredAdapter(policy)
        model_id = hashlib.sha256(policy.checkpoint.read_bytes()).hexdigest() if policy.checkpoint else "rule"
        self.policy_signature = f"{policy.policy}:{model_id}"
        self.timeout = number(command_timeout, "command_timeout", minimum=0.001)
        self.retry_interval = number(retry_interval, "retry_interval", minimum=0.001)
        self.clock = clock
        self.lock = threading.RLock()
        if str(database) != ":memory:":
            Path(database).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(database), check_same_thread=False, timeout=10)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS runtime (id INTEGER PRIMARY KEY, body TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS receipts (request_id TEXT PRIMARY KEY, digest TEXT, response TEXT)")
        self.db.commit()

    def close(self):
        with self.lock:
            self.db.close()

    def handle(self, request):
        """request_id 去重跨重启生效。响应丢失时，重试相同请求可取回原响应。"""
        try:
            finite_tree(request)
            rid = identifier(request.get("request_id"), "request_id")
            digest = hashlib.sha256(_json(request).encode()).hexdigest()
            with self.lock:
                self.db.execute("BEGIN IMMEDIATE")
                try:
                    old = self.db.execute("SELECT digest,response FROM receipts WHERE request_id=?", (rid,)).fetchone()
                    if old:
                        if old[0] != digest:
                            raise SnapshotError("request_id reused with different payload")
                        self.db.rollback()
                        return json.loads(old[1])
                    row = self.db.execute("SELECT body FROM runtime WHERE id=1").fetchone()
                    doc = json.loads(row[0]) if row else None
                    result, doc = self._execute(request, doc)
                    result.update(status="ok", request_id=rid, revision=doc["revision"])
                    self.db.execute("INSERT OR REPLACE INTO runtime VALUES (1,?)", (_json(doc),))
                    self.db.execute("INSERT INTO receipts VALUES (?,?,?)", (rid, digest, _json(result)))
                    self.db.commit()
                    return result
                except Exception:
                    self.db.rollback()
                    raise
        except (ValueError, KeyError, TypeError, AttributeError, OverflowError, RecursionError) as exc:
            return {"status": "error", "request_id": request.get("request_id") if isinstance(request, dict) else None,
                    "error": str(exc)[:300]}

    def _env(self, doc):
        return make_live_env(doc["snapshot"], critical_path=self.adapter.policy.critical_path)

    @staticmethod
    def _revision(request, doc):
        if type(request.get("expected_revision")) is not int or request["expected_revision"] != doc["revision"]:
            raise SnapshotError("stale revision; read state and plan again")

    def _execute(self, request, doc):
        op = request.get("operation")
        if op == "initialize":
            if doc is not None:
                raise SnapshotError("already initialized; use telemetry/feedback or a new mission database")
            snapshot = deepcopy(request["snapshot"])
            env = make_live_env(snapshot, critical_path=self.adapter.policy.critical_path)
            # Existing live assignments must be adopted by their execution IDs,
            # not imported without command ownership at startup.
            if env.state.active_assignments():
                raise SnapshotError("initialize requires no running assignments")
            snapshot.setdefault("request_uav_id", env.agents[0])
            if snapshot["request_uav_id"] not in env.agents:
                raise SnapshotError("request_uav_id not found in resource owners")
            doc = {"revision": 1, "snapshot": state_snapshot(env, snapshot),
                   "commands": {}, "plans": {}, "wall_time": self.clock(),
                   "contract_hash": contract_hash(self.adapter.policy.contract),
                   "policy_signature": self.policy_signature}
            return {"snapshot": doc["snapshot"]}, doc
        if doc is None:
            raise SnapshotError("initialize a mission first")
        if doc["contract_hash"] != contract_hash(self.adapter.policy.contract) or doc["policy_signature"] != self.policy_signature:
            raise SnapshotError("database observation contract differs from selected policy")
        if op == "state":
            tasks = doc["snapshot"]["task_graph"]["subtasks"]
            summary = {name: sum(t["state"] == name for t in tasks)
                       for name in ("pending", "ready", "running", "finished", "failed")}
            summary["total_tasks"] = len(tasks)
            summary["all_finished"] = all(t["state"] == "finished" for t in tasks)
            return {"snapshot": doc["snapshot"], "commands": list(doc["commands"].values()), "summary": summary}, doc
        if op in {"plan", "commit", "telemetry", "add_tasks", "cancel", "retry_task", "add_resources"}:
            self._revision(request, doc)
        if op == "schedule":
            # A server tick owns the current revision while holding the transaction.
            self._execute({"operation": "sweep", **{k:request[k] for k in ("at",) if k in request}}, doc)
            planned, doc = self._execute({"operation": "plan", "expected_revision": doc["revision"]}, doc)
            if not planned["plan"]["allocations"]:
                return {"plan": planned["plan"], "commands": []}, doc
            return self._execute({"operation": "commit", "expected_revision": doc["revision"],
                                  "plan_id": planned["plan"]["plan_id"]}, doc)
        if op == "plan":
            # Only the observed/mission clock advances; completion still requires feedback.
            self._time(request, doc)
            doc["snapshot"] = state_snapshot(self._env(doc), doc["snapshot"])
            started = time.perf_counter()
            proposal = self.adapter.decide(doc["snapshot"])
            proposal["decision_ms"] = (time.perf_counter()-started)*1000
            pid = uuid.uuid4().hex
            proposal.update(plan_id=pid, based_on_revision=doc["revision"])
            doc["plans"][pid] = proposal
            # Retain the latest plans; a discarded plan must be recomputed.
            if len(doc["plans"]) > 64:
                doc["plans"].pop(next(iter(doc["plans"])))
            return {"plan": proposal}, doc
        self._time(request, doc)
        if op == "commit":
            plan = doc["plans"].get(request.get("plan_id"))
            if plan is None or plan["based_on_revision"] != doc["revision"]:
                raise SnapshotError("unknown or stale plan")
            env = self._env(doc)
            commands = []
            for allocation in plan["allocations"]:
                record = env.executor.assign(env.state, allocation["subtask_id"], allocation["resource_id"])
                cmd_id = uuid.uuid4().hex
                resource = env.state.get_resource(record.resource_id)
                cmd = {"command_id": cmd_id, "uav_id": resource.owner_uav_id,
                       "subtask_id": record.subtask_id, "resource_id": record.resource_id,
                       "resource_type": resource.resource_type,
                       "task": asdict(env.state.get_subtask(record.subtask_id)),
                       "status": "queued", "created_at": env.state.now,
                       "deadline_at": env.state.now + self.timeout,
                       "last_event_time": env.state.now, "attempts": 0,
                       "estimated_energy": record.estimated_energy,
                       "reserved_execution_energy": record.estimated_energy-record.communication_energy,
                       "estimated_end_time": record.completion_time,
                       "energy_kind": "estimated", "plan_id": plan["plan_id"]}
                inputs = []
                for edge in env.state.task_graph.edges:
                    if edge.dst_subtask_id == record.subtask_id:
                        prior = [c for c in doc["commands"].values() if c["subtask_id"] == edge.src_subtask_id
                                 and c["status"] == "completed"]
                        inputs.append({"subtask_id": edge.src_subtask_id, "data_size_mb": edge.data_size_mb,
                                       "outputs": prior[-1].get("outputs", {}) if prior else {}})
                cmd["inputs"] = inputs
                doc["commands"][cmd_id] = cmd; commands.append(deepcopy(cmd))
            doc["snapshot"] = state_snapshot(env, doc["snapshot"])
            self._changed(doc)
            return {"commands": commands}, doc
        if op == "poll_commands":
            owner = identifier(request.get("uav_id"), "uav_id")
            worker = identifier(request.get("worker_id"), "worker_id")
            now = doc["snapshot"]["time"]
            commands = []
            for command in doc["commands"].values():
                if (command["uav_id"] != owner or command["status"] in FINAL
                        or command.get("worker_id", worker) != worker):
                    continue
                if command["status"] != "cancelling" and now >= command["deadline_at"]:
                    command["status"] = "cancelling"
                    command["cancel_reason"] = "execution_timeout"
                if (command["status"] in {"queued", "dispatched", "cancelling"}
                        and now >= command.get("next_delivery_at", -1)):
                    command["attempts"] += 1
                    command["worker_id"] = worker
                    command["next_delivery_at"] = now + self.retry_interval
                    if command["status"] != "cancelling":
                        command["status"] = "dispatched"
                    commands.append({**deepcopy(command), "operation":
                                     "cancel" if command["status"] == "cancelling" else "execute",
                                     "delivery_time": now})
            # Delivery leases do not change the task/resource revision.
            return {"commands": commands}, doc
        if op == "feedback":
            return self._feedback(request, doc), doc
        if op == "sweep":
            expired = []
            for command in doc["commands"].values():
                if command["status"] in ACTIVE - {"cancelling"} and doc["snapshot"]["time"] >= command["deadline_at"]:
                    self._cancel(command, "execution_timeout"); expired.append(command["command_id"])
            if expired:
                self._changed(doc)
            return {"cancelling": expired}, doc
        if op == "cancel":
            command = doc["commands"][request["command_id"]]
            if command["status"] not in ACTIVE:
                raise SnapshotError("command already terminal")
            self._cancel(command, "requested")
            self._changed(doc)
            return {"command": command}, doc
        if op == "telemetry":
            return self._telemetry(request, doc), doc
        if op == "retry_task":
            env = self._env(doc); task = env.state.get_subtask(request["subtask_id"])
            if task.state != "failed":
                raise SnapshotError("only confirmed failed/cancelled tasks can be retried")
            task.state = "pending"; env.state.task_graph.update_ready_states(env.state.now)
            doc["snapshot"] = state_snapshot(env, doc["snapshot"]); self._changed(doc)
            return {"subtask_id": task.subtask_id, "task_state": task.state}, doc
        if op == "add_resources":
            candidate = deepcopy(doc["snapshot"])
            candidate["resource_graph"]["resources"].extend(deepcopy(request["resources"]))
            env = make_live_env(candidate, critical_path=self.adapter.policy.critical_path)
            doc["snapshot"] = state_snapshot(env, candidate); self._changed(doc)
            return {"added":len(request["resources"])}, doc
        if op == "add_tasks":
            raw_check = deepcopy(doc["snapshot"])
            raw_check["task_graph"]["subtasks"].extend(deepcopy(entry["task"]) for entry in request["tasks"])
            make_live_env(raw_check, critical_path=self.adapter.policy.critical_path)
            env = self._env(doc)
            for entry in request["tasks"]:
                env.state.add_subtask(SubTask.from_dict(entry["task"]), entry.get("predecessors", []),
                                      entry.get("predecessor_data_sizes"))
            candidate = state_snapshot(env, doc["snapshot"])
            make_live_env(candidate, critical_path=self.adapter.policy.critical_path)
            doc["snapshot"] = candidate; self._changed(doc)
            return {"added": len(request["tasks"])}, doc
        raise SnapshotError("unknown operation")

    def _time(self, request, doc):
        snapshot = doc["snapshot"]
        now = request.get("at", snapshot["time"] + max(0, self.clock() - doc["wall_time"]))
        snapshot["time"] = number(now, "at", minimum=snapshot["time"])
        snapshot["resource_graph"]["timestamp"] = snapshot["time"]
        doc["wall_time"] = self.clock()

    @staticmethod
    def _changed(doc):
        doc["revision"] += 1
        doc["plans"] = {}
        doc["snapshot"]["snapshot_id"] = f"runtime-{doc['revision']}"

    @staticmethod
    def _cancel(command, reason):
        command["status"] = "cancelling"
        command["cancel_reason"] = reason
        command["next_delivery_at"] = -1
        # Resource stays occupied until stopped/completed feedback arrives.

    def _feedback(self, request, doc):
        command = doc["commands"][request["command_id"]]
        worker = identifier(request.get("worker_id"), "worker_id")
        if request.get("uav_id") != command["uav_id"] or worker != command.get("worker_id"):
            raise SnapshotError("feedback owner/worker mismatch")
        status = request.get("result")
        if status not in {"accepted", "running", *FINAL}:
            raise SnapshotError("unsupported feedback result")
        if command["status"] in FINAL:
            if status != command["status"]:
                raise SnapshotError("terminal command cannot change result")
            return {"command": command}
        when = number(request.get("event_time", doc["snapshot"]["time"]), "event_time",
                      minimum=command["last_event_time"], maximum=doc["snapshot"]["time"])
        if command["status"] == "cancelling" and status not in FINAL:
            raise SnapshotError("cancelling command requires stopped/completed feedback")
        if command["status"] == "running" and status == "accepted":
            raise SnapshotError("feedback would regress execution state")
        command["status"] = status; command["last_event_time"] = when
        if "detail" in request:
            if not isinstance(request["detail"], str) or len(request["detail"]) > 1000:
                raise SnapshotError("invalid feedback detail")
            command["detail"] = request["detail"]
        if "outputs" in request:
            outputs = request["outputs"]
            if not isinstance(outputs, dict) or len(outputs) > 32:
                raise SnapshotError("outputs must be a small name-to-URI mapping")
            for key, value in outputs.items():
                identifier(key, "output name")
                if not isinstance(value, str) or not value or len(value) > 4096:
                    raise SnapshotError("invalid output URI")
            command["outputs"] = outputs
        if status == "running":
            command.setdefault("actual_start_time", when)
        if status in FINAL:
            env = self._env(doc)
            task, resource = env.state.get_subtask(command["subtask_id"]), env.state.get_resource(command["resource_id"])
            active = [a for a in env.state.active_assignments() if a.subtask_id == task.subtask_id
                      and a.resource_id == resource.resource_id]
            if len(active) != 1:
                raise SnapshotError("command does not own active assignment")
            record = active[0]
            record.status = "finished" if status == "completed" else "failed"
            record.actual_end_time = when
            task.state = "finished" if status == "completed" else "failed"
            resource.occupied = False; resource.release_time = when
            for transfer in env.state.transfer_reservations:
                if transfer.subtask_id == task.subtask_id and transfer.resource_id == resource.resource_id:
                    transfer.status = "finished" if status == "completed" else "cancelled"
            # Optional measured execution energy excludes sender-side transfer energy.
            if "execution_energy_used" in request:
                measured = number(request["execution_energy_used"], "execution_energy_used")
                reserved_execution = command["reserved_execution_energy"]
                resource.remaining_energy = max(0, resource.remaining_energy + reserved_execution - measured)
                command["execution_energy_used"] = measured
                command["energy_kind"] = "execution_measured_transfer_estimated"
            command["actual_end_time"] = when
            env.state.task_graph.update_ready_states(env.state.now)
            doc["snapshot"] = state_snapshot(env, doc["snapshot"])
        self._changed(doc)
        return {"command": command}

    def _telemetry(self, request, doc):
        snapshot = doc["snapshot"]
        allowed = {"location", "modalities", "sensing_quality", "detection_range", "power", "cpu_frequency",
                   "queue_length", "link_rate", "remaining_energy", "online", "occupied", "release_time"}
        resources = {r["resource_id"]: r for r in snapshot["resource_graph"]["resources"]}
        changed_offline = set()
        patches = list(request.get("resources", []))
        for report in request.get("assessments", []):
            patch = assessment_patch(report)
            current = resources[patch["resource_id"]].get("sensing_quality", {})
            patch["sensing_quality"] = {**current, **patch["sensing_quality"]}
            patches.append(patch)
        for patch in patches:
            rid = patch["resource_id"]
            if not set(patch) <= allowed | {"resource_id"}:
                raise SnapshotError("telemetry cannot change resource ownership/occupancy")
            if set(patch) & {"occupied", "release_time"} and any(
                    c["resource_id"] == rid and c["status"] in ACTIVE for c in doc["commands"].values()):
                raise SnapshotError("telemetry cannot release a resource owned by an active command")
            resources[rid].update(patch)
            if patch.get("online") is False:
                changed_offline.add(rid)
        links = {(x["source_uav_id"], x["target_uav_id"]): x
                 for x in snapshot["resource_graph"].get("communication_links", [])}
        offline_links = set()
        for patch in request.get("links", []):
            pair = patch["source_uav_id"], patch["target_uav_id"]
            if not set(patch) <= {"source_uav_id", "target_uav_id", "bandwidth_mb_s", "latency_s", "energy_per_mb", "online"}:
                raise SnapshotError("unsupported link telemetry field")
            links[pair].update(patch)
            if patch.get("online") is False:
                offline_links.add(pair)
        for command in doc["commands"].values():
            affected_link = any(t["subtask_id"] == command["subtask_id"] and
                                (t["source_uav_id"], t["target_uav_id"]) in offline_links and
                                t["status"] not in {"finished", "cancelled"}
                                for t in snapshot.get("transfer_reservations", []))
            if command["status"] in ACTIVE and (command["resource_id"] in changed_offline or affected_link):
                self._cancel(command, "resource_or_link_offline")
        env = self._env(doc)
        doc["snapshot"] = state_snapshot(env, snapshot); self._changed(doc)
        return {"snapshot": doc["snapshot"]}
