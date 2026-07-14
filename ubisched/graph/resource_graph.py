from __future__ import annotations

"""异构资源图的数据模型。

第一阶段不实现资源边。传感器和计算节点是可执行资源，UAV 仅通过
owner_uav_id 表示资源归属，通信能力暂由节点自身的 link_rate 表示。
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List


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
        )


@dataclass
class ResourceGraph:
    """同一时间戳下全部可执行资源节点的集合。"""
    resource_graph_id: str
    timestamp: float
    resources: List[ResourceNode]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResourceGraph":
        """从配置构建资源快照，并在 ResourceNode 中校验资源类型。"""
        return cls(
            resource_graph_id=str(data["resource_graph_id"]),
            timestamp=float(data.get("timestamp", 0.0)),
            resources=[
                ResourceNode.from_dict(item) for item in data.get("resources", [])
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
