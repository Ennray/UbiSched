from __future__ import annotations

"""异构资源图的数据模型。

传感器和计算节点是可执行资源，UAV 通过 owner_uav_id 表示资源归属。
显式数据依赖使用 UAV 间有向通信链路；无显式数据依赖的旧场景保留
link_rate 兼容计算。通信预约与状态保存在 SchedulingState。
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List
import math


EXECUTABLE_RESOURCE_TYPES = {"sensor", "compute"}


def _load_structured_file(path: str | Path) -> Dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
    except ModuleNotFoundError:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data


@dataclass
class ResourceNode:
    """某一时刻可参与任务分配的传感器或计算资源快照。

    sensing_quality 按模态记录质量，例如 {"camera": 0.9}；occupied 和
    release_time 共同描述动态可用性，remaining_energy 描述续航约束。
    """
    resource_id: str
    resource_type: str
    owner_uav_id: str | None
    location: List[float]
    modalities: List[str]
    sensing_quality: Dict[str, float]
    detection_range: float
    power: float
    cpu_frequency: float
    queue_length: float
    link_rate: float
    remaining_energy: float
    occupied: bool
    release_time: float
    online: bool = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResourceNode":
        resource_type = str(data["resource_type"])
        # UAV 是资源载体而非动作目标，因此不能作为 ResourceNode 的可执行类型。
        if resource_type not in EXECUTABLE_RESOURCE_TYPES:
            raise ValueError(
                f"Unsupported executable resource_type: {resource_type}. "
                "First step only supports sensor and compute."
            )
        return cls(
            resource_id=str(data["resource_id"]),
            resource_type=resource_type,
            owner_uav_id=(
                None
                if data.get("owner_uav_id") is None
                else str(data.get("owner_uav_id"))
            ),
            location=[float(v) for v in data.get("location", [0.0, 0.0, 0.0])],
            modalities=[str(v) for v in data.get("modalities", [])],
            sensing_quality={
                str(k): float(v) for k, v in data.get("sensing_quality", {}).items()
            },
            detection_range=float(data.get("detection_range", 0.0)),
            power=float(data.get("power", 0.0)),
            cpu_frequency=float(data.get("cpu_frequency", 0.0)),
            queue_length=float(data.get("queue_length", 0.0)),
            link_rate=float(data.get("link_rate", 0.0)),
            remaining_energy=float(data.get("remaining_energy", 0.0)),
            occupied=bool(data.get("occupied", False)),
            release_time=float(data.get("release_time", 0.0)),
            online=bool(data.get("online", True)),
        )



@dataclass
class CommunicationLink:
    """UAV 之间的有向直连通信路径。

    bandwidth_mb_s 为 MB/s，latency_s 为单次传输的固定时延，
    energy_per_mb 为发送侧每 MB 能耗。当前同一有向链路采用独占
    时段预约与串行传输，不支持多跳或共享无线电跨链路争用。
    """
    source_uav_id: str
    target_uav_id: str
    bandwidth_mb_s: float
    latency_s: float = 0.0
    energy_per_mb: float = 0.0
    online: bool = True

    def __post_init__(self):
        if (not all(math.isfinite(v) for v in (
                self.bandwidth_mb_s, self.latency_s, self.energy_per_mb))
            or self.bandwidth_mb_s <= 0 or self.latency_s < 0
            or self.energy_per_mb < 0
            or self.source_uav_id == self.target_uav_id):
            raise ValueError("Invalid communication link parameters")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CommunicationLink":
        return cls(
            source_uav_id=str(data["source_uav_id"]),
            target_uav_id=str(data["target_uav_id"]),
            bandwidth_mb_s=float(data["bandwidth_mb_s"]),
            latency_s=float(data.get("latency_s", 0.0)),
            energy_per_mb=float(data.get("energy_per_mb", 0.0)),
            online=bool(data.get("online", True)),
        )


@dataclass
class ResourceGraph:
    """同一时间戳下全部可执行资源节点的集合。"""
    resource_graph_id: str
    timestamp: float
    resources: List[ResourceNode]
    communication_links: List[CommunicationLink] = field(default_factory=list)

    def __post_init__(self):
        pairs = [(link.source_uav_id, link.target_uav_id)
                 for link in self.communication_links]
        if len(pairs) != len(set(pairs)):
            raise ValueError("Duplicate direct communication link")

    def set_link_online(self, source_uav_id: str, target_uav_id: str, online: bool) -> None:
        """模拟运行期间的通信中断或恢复；下一次匹配立即采用新的连接状态。"""
        for link in self.communication_links:
            if link.source_uav_id == source_uav_id and link.target_uav_id == target_uav_id:
                link.online = bool(online)
                return
        raise KeyError(f"Unknown link {source_uav_id} -> {target_uav_id}")

    def get_link(self, source_uav_id: str, target_uav_id: str) -> CommunicationLink | None:
        return next((link for link in self.communication_links
                     if link.source_uav_id == source_uav_id
                     and link.target_uav_id == target_uav_id and link.online), None)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResourceGraph":
        """从配置构建资源快照，并在 ResourceNode 中校验资源类型。"""
        return cls(
            resource_graph_id=str(data["resource_graph_id"]),
            timestamp=float(data.get("timestamp", 0.0)),
            resources=[
                ResourceNode.from_dict(item) for item in data.get("resources", [])
            ],
            communication_links=[
                CommunicationLink.from_dict(item)
                for item in data.get("communication_links", [])
            ],
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> "ResourceGraph":
        return cls.from_dict(_load_structured_file(path))

    def resource_ids(self) -> List[str]:
        return [resource.resource_id for resource in self.resources]

    def summary(self) -> str:
        type_counts: Dict[str, int] = {}
        for resource in self.resources:
            type_counts[resource.resource_type] = (
                type_counts.get(resource.resource_type, 0) + 1
            )
        return (
            f"ResourceGraph(id={self.resource_graph_id}, "
            f"resources={len(self.resources)}, types={type_counts})"
        )
