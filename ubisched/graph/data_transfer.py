from __future__ import annotations

"""跨 UAV 数据传输计划：按有向链路容量预约互斥时段。

估算函数是纯读取操作；只有执行器接受分配之后才把计划写入调度状态。
每个有向链路同时只承载一项传输，不同链路可并行。数据依赖的多个
前序输入仍按保守串行方式聚合，暂不支持多跳路由和分片传输。
"""

from dataclasses import dataclass, field
from typing import Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from ubisched.scheduling.scheduling_state import SchedulingState


@dataclass(frozen=True)
class TransferHop:
    source_resource_id: str
    source_uav_id: str
    target_uav_id: str
    data_size_mb: float
    latency_s: float
    energy: float
    start_time: float = 0.0
    end_time: float = 0.0
    queue_wait_s: float = 0.0


@dataclass
class DataTransferEstimate:
    feasible: bool = True
    has_data_edges: bool = False
    latency: float = 0.0
    energy: float = 0.0
    source_energy_debits: Dict[str, float] = field(default_factory=dict)
    hops: List[TransferHop] = field(default_factory=list)
    queue_wait_s: float = 0.0


def _earliest_link_slot(state: SchedulingState, source: str, target: str,
                        earliest: float, duration: float,
                        tentative: List[TransferHop]) -> float:
    """在现有预约之间寻找最早空档；不修改已预约的传输。"""
    slots = [(x.start_time, x.end_time) for x in state.transfer_reservations
             if x.status != 'cancelled' and x.source_uav_id == source
             and x.target_uav_id == target and x.end_time > state.now]
    slots += [(x.start_time, x.end_time) for x in tentative
              if x.source_uav_id == source and x.target_uav_id == target]
    start = earliest
    for lo, hi in sorted(slots):
        if start + duration <= lo + 1e-9:
            break
        if start < hi - 1e-9 and start + duration > lo + 1e-9:
            start = hi
    return start


def estimate_data_transfer(state: SchedulingState, subtask_id: str,
                           target_resource_id: str) -> DataTransferEstimate:
    """考虑同链路传输预约、排队时延和发送端能量后的可行性估算。"""
    target = state.get_resource(target_resource_id)
    result = DataTransferEstimate()
    cursor = state.now
    for edge in state.task_graph.edges:
        if edge.dst_subtask_id != subtask_id or edge.data_size_mb <= 0:
            continue
        result.has_data_edges = True
        predecessors = [a for a in state.assignments
                        if a.subtask_id == edge.src_subtask_id and a.status == 'finished']
        if not predecessors:
            return DataTransferEstimate(feasible=False)
        source = state.get_resource(predecessors[-1].resource_id)
        if not source.owner_uav_id or not target.owner_uav_id:
            return DataTransferEstimate(feasible=False)
        if source.owner_uav_id == target.owner_uav_id:
            continue
        link = state.resource_graph.get_link(source.owner_uav_id, target.owner_uav_id)
        if link is None:
            return DataTransferEstimate(feasible=False)
        duration = link.latency_s + edge.data_size_mb / link.bandwidth_mb_s
        start = _earliest_link_slot(state, source.owner_uav_id, target.owner_uav_id,
                                    cursor, duration, result.hops)
        end = start + duration
        wait = max(0.0, start - cursor)
        energy = edge.data_size_mb * link.energy_per_mb
        result.queue_wait_s += wait
        result.energy += energy
        result.source_energy_debits[source.resource_id] = (
            result.source_energy_debits.get(source.resource_id, 0.0) + energy
        )
        result.hops.append(TransferHop(
            source_resource_id=source.resource_id,
            source_uav_id=source.owner_uav_id,
            target_uav_id=target.owner_uav_id,
            data_size_mb=edge.data_size_mb,
            latency_s=duration,
            energy=energy,
            start_time=start,
            end_time=end,
            queue_wait_s=wait,
        ))
        cursor = end
    result.latency = cursor - state.now
    if any(state.get_resource(rid).remaining_energy + 1e-9 < energy
           for rid, energy in result.source_energy_debits.items()):
        return DataTransferEstimate(feasible=False)
    return result
