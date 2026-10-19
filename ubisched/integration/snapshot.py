"""校验外部观测并恢复环境。这里不推进仿真，也不推定任务完成。"""
from dataclasses import fields
import math
from typing import Any

from ubisched.config import make_env
from ubisched.graph.task_graph import TaskGraph
from ubisched.graph.resource_graph import ResourceGraph
from ubisched.scheduling.scheduling_state import AssignmentRecord, TransferReservation


class SnapshotError(ValueError):
    pass


def finite_tree(value: Any):
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise SnapshotError("non-string key")
            finite_tree(item)
    elif isinstance(value, list):
        for item in value:
            finite_tree(item)
    elif isinstance(value, float) and not math.isfinite(value):
        raise SnapshotError("non-finite number")


def number(value, name, *, minimum=0, maximum=None):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or value < minimum or (maximum is not None and value > maximum)):
        raise SnapshotError(f"invalid {name}")
    return float(value)


def identifier(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise SnapshotError(f"invalid {name}")
    return value


def _nodes(data):
    tg, rg = data["task_graph"], data["resource_graph"]
    identifier(tg.get("task_graph_id"), "task_graph_id")
    identifier(rg.get("resource_graph_id"), "resource_graph_id")
    for t in tg.get("subtasks", []):
        identifier(t.get("subtask_id"), "subtask_id")
        identifier(t.get("task_type"), "task_type")
        for key in ("priority", "deadline", "data_size", "compute_cycles", "max_latency", "arrival_time"):
            number(t.get(key, 0), key)
        number(t.get("min_quality", 0), "min_quality", maximum=1)
        for key in ("resource_count_min", "resource_count_max"):
            if type(t.get(key, 1)) is not int or t.get(key, 1) != 1:
                raise SnapshotError("only one resource per task is supported")
        if t.get("state", "pending") not in {"pending", "ready", "running", "finished", "failed"}:
            raise SnapshotError("unsupported task state")
    for r in rg.get("resources", []):
        identifier(r.get("resource_id"), "resource_id")
        identifier(r.get("owner_uav_id"), "owner_uav_id")
        for key in ("detection_range", "power", "cpu_frequency", "queue_length", "link_rate",
                    "remaining_energy", "release_time"):
            number(r.get(key, 0), key)
        for value in r.get("sensing_quality", {}).values():
            number(value, "sensing_quality", maximum=1)
        for key in ("online", "occupied"):
            if type(r.get(key, key == "online")) is not bool:
                raise SnapshotError(f"{key} must be boolean")
    for node in [*tg.get("subtasks", []), *rg.get("resources", [])]:
        location = node.get("location", [0, 0, 0])
        if not isinstance(location, list) or len(location) not in (2, 3):
            raise SnapshotError("location must be 2D or 3D")
        for value in location:
            number(value, "location", minimum=-1e12)
    for edge in tg.get("edges", []):
        number(edge.get("data_size_mb", 0), "data_size_mb")
    for link in rg.get("communication_links", []):
        identifier(link.get("source_uav_id"), "source_uav_id")
        identifier(link.get("target_uav_id"), "target_uav_id")
        if type(link.get("online", True)) is not bool:
            raise SnapshotError("link online must be boolean")
        for key in ("bandwidth_mb_s", "latency_s", "energy_per_mb"):
            number(link.get(key, 0), key)


def _validate_graphs(tasks, resources):
    tids, rids = tasks.subtask_ids(), resources.resource_ids()
    if not tids or not rids or len(tids) != len(set(tids)) or len(rids) != len(set(rids)):
        raise SnapshotError("task/resource IDs must be nonempty and unique")
    adj, indeg = {x: [] for x in tids}, {x: 0 for x in tids}
    edges = set()
    for edge in tasks.edges:
        pair = edge.src_subtask_id, edge.dst_subtask_id
        if pair in edges or pair[0] not in adj or pair[1] not in adj or pair[0] == pair[1]:
            raise SnapshotError("duplicate or invalid task edge")
        edges.add(pair); adj[pair[0]].append(pair[1]); indeg[pair[1]] += 1
    queue = [x for x in tids if indeg[x] == 0]
    count = 0
    while queue:
        cur = queue.pop(); count += 1
        for nxt in adj[cur]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    if count != len(tids):
        raise SnapshotError("task graph contains cycle")
    owners = {r.owner_uav_id for r in resources.resources}
    for link in resources.communication_links:
        if link.source_uav_id not in owners or link.target_uav_id not in owners:
            raise SnapshotError("link references unknown UAV")


def make_live_env(snapshot, *, critical_path=False):
    try:
        return _make_live_env(snapshot, critical_path=critical_path)
    except (KeyError, TypeError, AttributeError, OverflowError) as exc:
        raise SnapshotError(f"invalid snapshot structure: {exc}") from exc


def _make_live_env(snapshot, *, critical_path=False):
    if not isinstance(snapshot, dict) or type(snapshot.get("version")) is not int or snapshot["version"] != 2:
        raise SnapshotError("expected version=2 snapshot")
    finite_tree(snapshot); _nodes(snapshot)
    number(snapshot["task_graph"].get("created_time", 0), "created_time")
    number(snapshot["resource_graph"].get("timestamp", 0), "timestamp")
    tasks = TaskGraph.from_dict(snapshot["task_graph"])
    resources = ResourceGraph.from_dict(snapshot["resource_graph"])
    _validate_graphs(tasks, resources)
    now = number(snapshot.get("time", resources.timestamp), "time")
    resources.timestamp = now
    # Critical-path features need active records. Initialize the base environment
    # first, restore records, then enable the derived feature branch.
    env = make_env(tasks, resources, critical_path=False)
    env.reset(); state = env.state
    if "energy_normalization" in snapshot:
        env._base._resource_energy_scale = number(snapshot["energy_normalization"], "energy_normalization", minimum=1)
    seen_finished, seen_running, busy_resources = set(), set(), set()
    for rec in snapshot.get("completed_assignments", []):
        tid, rid = rec["subtask_id"], rec["resource_id"]
        task = state.get_subtask(tid); state.get_resource(rid)
        if task.state != "finished" or tid in seen_finished:
            raise SnapshotError("completed assignment inconsistent with finished task")
        source = state.get_resource(rid)
        expected_type = "sensor" if task.task_type in {"sense", "detect", "track"} else "compute"
        if source.resource_type != expected_type:
            raise SnapshotError("completed task/resource type mismatch")
        finish = number(rec.get("end_time", now), "end_time", minimum=task.arrival_time, maximum=now)
        seen_finished.add(tid)
        state.assignments.append(AssignmentRecord(tid, rid, finish, finish, 0, 0,
            status="finished", actual_end_time=finish))
    for rec in snapshot.get("running_assignments", []):
        tid, rid = rec["subtask_id"], rec["resource_id"]
        task, resource = state.get_subtask(tid), state.get_resource(rid)
        start = number(rec["start_time"], "start_time", maximum=now)
        end = number(rec["completion_time"], "completion_time", minimum=start)
        if task.state != "running" or tid in seen_running or rid in busy_resources or not resource.occupied:
            raise SnapshotError("inconsistent running assignment")
        seen_running.add(tid); busy_resources.add(rid)
        state.assignments.append(AssignmentRecord(tid, rid, start, end, end-start,
            number(rec.get("estimated_energy", 0), "estimated_energy")))
    if {t.subtask_id for t in state.task_graph.subtasks if t.state == "running"} != seen_running:
        raise SnapshotError("running task requires running_assignments")
    for rec in snapshot.get("transfer_reservations", []):
        reservation = TransferReservation(**rec)
        state.get_subtask(reservation.subtask_id); state.get_resource(reservation.resource_id)
        source = state.get_resource(reservation.source_resource_id)
        target = state.get_resource(reservation.resource_id)
        if (source.owner_uav_id != reservation.source_uav_id or target.owner_uav_id != reservation.target_uav_id
                or reservation.status not in {"queued", "transferring", "finished", "cancelled"}):
            raise SnapshotError("invalid transfer reservation identity/status")
        for key in ("start_time", "end_time", "data_size_mb", "energy"):
            number(getattr(reservation, key), key)
        if reservation.start_time > reservation.end_time:
            raise SnapshotError("invalid transfer reservation time range")
        state.transfer_reservations.append(reservation)
    for edge in tasks.edges:
        if edge.data_size_mb > 0 and state.get_subtask(edge.src_subtask_id).state == "finished":
            if edge.src_subtask_id not in seen_finished:
                raise SnapshotError("missing completed assignment for data predecessor")
    for task in state.task_graph.subtasks:
        if task.state in {"running", "finished"}:
            if task.arrival_time > now or any(
                    state.get_subtask(e.src_subtask_id).state != "finished"
                    for e in tasks.edges if e.dst_subtask_id == task.subtask_id):
                raise SnapshotError("active/completed task violates arrival or dependency")
    slots = {}
    for transfer in state.transfer_reservations:
        if transfer.status not in {"finished", "cancelled"}:
            pair = (transfer.source_uav_id, transfer.target_uav_id)
            slots.setdefault(pair, []).append((transfer.start_time, transfer.end_time))
    for intervals in slots.values():
        intervals.sort()
        if any(intervals[i][0] < intervals[i-1][1]-1e-9 for i in range(1,len(intervals))):
            raise SnapshotError("overlapping exclusive link reservations")
    state.task_graph.update_ready_states(now)
    env.include_critical_path_features = bool(critical_path)
    return env
