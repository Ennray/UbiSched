from __future__ import annotations

"""基于规则的任务节点与资源节点两两匹配。

矩阵的行对应 SubTask，列对应 ResourceNode。每个单元格先进行硬约束
可行性判定，再计算用于比较可行资源优劣的软评分。
"""

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from ubisched.graph.resource_graph import ResourceGraph, ResourceNode
from ubisched.graph.task_graph import SubTask, TaskGraph
from ubisched.graph.data_transfer import DataTransferEstimate, estimate_data_transfer
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ubisched.scheduling.scheduling_state import SchedulingState


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


def _clamp01(value: float) -> float:
    """把归一化结果限制在 [0, 1]，避免极端输入放大评分。"""
    return max(0.0, min(1.0, value))


def _distance(a: List[float], b: List[float]) -> float:
    """计算二维或三维欧氏距离，缺少的坐标维度按 0 补齐。"""
    size = max(len(a), len(b))
    aa = a + [0.0] * (size - len(a))
    bb = b + [0.0] * (size - len(b))
    return math.sqrt(sum((aa[i] - bb[i]) ** 2 for i in range(size)))


@dataclass
class MatchEntry:
    """一个 SubTask-ResourceNode 组合的完整匹配结果。"""
    feasible: bool
    quality_score: float
    latency_cost: float
    energy_cost: float
    distance_cost: float
    load_cost: float
    match_score: float

    def as_vector(self) -> List[float]:
        return [
            1.0 if self.feasible else 0.0,
            self.quality_score,
            self.latency_cost,
            self.energy_cost,
            self.distance_cost,
            self.load_cost,
            self.match_score,
        ]


@dataclass(frozen=True)
class ExecutionEstimate:
    """执行一个任务-资源组合时使用的原始时延和能耗估计。"""

    latency: float
    energy: float


@dataclass
class MatchMatrix:
    """任务数 N × 资源数 M 的匹配矩阵。"""
    subtask_ids: List[str]
    resource_ids: List[str]
    entries: List[List[MatchEntry]]

    @property
    def feasible(self) -> List[List[int]]:
        return [
            [1 if entry.feasible else 0 for entry in row] for row in self.entries
        ]

    @property
    def match_score(self) -> List[List[float]]:
        return [[entry.match_score for entry in row] for row in self.entries]

    def field_matrix(self, field_name: str) -> List[List[float]]:
        return [
            [float(getattr(entry, field_name)) for entry in row]
            for row in self.entries
        ]

    def as_tensor(self) -> List[List[List[float]]]:
        """转换为 N × M × 7 的数值张量形式，供后续算法直接消费。"""
        return [[entry.as_vector() for entry in row] for row in self.entries]


class RuleBasedScorer:
    """用透明、可配置的规则计算单个任务-资源组合的匹配结果。"""
    def __init__(self, config: Dict[str, Any] | None = None):
        self.config = config or {}
        # 旧版本保留硬截止时间；新实验可显式启用软截止时间。
        self.strict_deadlines = bool(self.config.get("strict_deadlines", True))
        self.normalization = self.config.get("normalization", {})
        self.defaults = self.config.get("defaults", {})
        self.weights = self.config.get(
            "match_weights",
            {
                "quality": 0.35,
                "latency": 0.25,
                "energy": 0.15,
                "distance": 0.10,
                "load": 0.10,
                "priority": 0.05,
            },
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> "RuleBasedScorer":
        return cls(_load_structured_file(path))

    def score(
        self,
        subtask: SubTask,
        resource: ResourceNode,
        current_time: float = 0.0,
        transfer: DataTransferEstimate | None = None,
    ) -> MatchEntry:
        """计算一个矩阵单元格。

        quality_score 是收益项，其余 cost 是代价项。feasible 是硬门槛：
        不可行组合的 match_score 固定为 0，不参与资源优选。
        """
        # 先计算原始物理量，再统一归一化，保证不同量纲可以加权组合。
        quality_score = self._quality_score(subtask, resource)
        distance = _distance(subtask.location, resource.location)
        estimate = self.estimate_execution(subtask, resource, current_time, transfer)
        latency = estimate.latency
        energy = estimate.energy
        distance_cost = self._normalize(distance, "max_distance")
        latency_cost = self._normalize(latency, "max_latency")
        energy_cost = self._normalize(energy, "max_energy")
        load_cost = self._normalize(resource.queue_length, "max_queue_length")
        priority_score = self._normalize(subtask.priority, "max_priority")

        feasible = (transfer is None or transfer.feasible) and self._is_feasible(
            subtask=subtask,
            resource=resource,
            quality_score=quality_score,
            distance=distance,
            latency=latency,
            energy=energy - (transfer.energy if transfer is not None else 0.0),
            current_time=current_time,
        )

        if feasible:
            # 质量和优先级提高得分；时延、能耗、距离和负载降低得分。
            match_score = (
                self.weights.get("quality", 0.0) * quality_score
                - self.weights.get("latency", 0.0) * latency_cost
                - self.weights.get("energy", 0.0) * energy_cost
                - self.weights.get("distance", 0.0) * distance_cost
                - self.weights.get("load", 0.0) * load_cost
                + self.weights.get("priority", 0.0) * priority_score
            )
            match_score = _clamp01(match_score)
        else:
            match_score = 0.0

        return MatchEntry(
            feasible=feasible,
            quality_score=quality_score,
            latency_cost=latency_cost,
            energy_cost=energy_cost,
            distance_cost=distance_cost,
            load_cost=load_cost,
            match_score=match_score,
        )

    def estimate_execution(
        self,
        subtask: SubTask,
        resource: ResourceNode,
        current_time: float = 0.0,
        transfer: DataTransferEstimate | None = None,
    ) -> ExecutionEstimate:
        """返回执行阶段可复用的原始时延和能耗估计。

        MatchMatrix 和 AssignmentExecutor 共用这个入口，保证匹配阶段的
        可行性判断与实际分配后的状态更新采用完全相同的估算公式。
        """
        # 仅累计真实需要的跨机传输时延。执行能耗按本机执行阶段计算，
        # 传输能耗另计入发送节点，避免把传输期间的等待算成本机CPU工作功耗。
        base_latency = self._latency(
            subtask, resource, current_time,
            include_legacy_transmission=not (transfer is not None and transfer.has_data_edges),
        )
        latency = base_latency + (transfer.latency if transfer is not None else 0.0)
        energy = self._energy(subtask, resource, base_latency)
        if transfer is not None:
            energy += transfer.energy
        return ExecutionEstimate(latency=latency, energy=energy)

    def _quality_score(self, subtask: SubTask, resource: ResourceNode) -> float:
        """计算资源对任务的有效质量，结果归一化到 [0, 1]。"""
        if resource.resource_type == "compute":
            # 计算资源频率越高越好，但已有队列会折损有效计算质量。
            max_cpu = float(self.normalization.get("max_cpu_frequency", 1.0))
            cpu_quality = resource.cpu_frequency / max(max_cpu, self._epsilon())
            load_penalty = self._normalize(resource.queue_length, "max_queue_length")
            return _clamp01(cpu_quality * (1.0 - 0.5 * load_penalty))

        if not subtask.required_modalities_any:
            return 0.0
        # any 语义：支持任一需求模态即可，多个命中时取其中最高质量。
        qualities = [
            resource.sensing_quality.get(modality, 0.0)
            for modality in subtask.required_modalities_any
            if modality in resource.modalities
        ]
        return _clamp01(max(qualities) if qualities else 0.0)

    def _latency(
        self, subtask: SubTask, resource: ResourceNode, current_time: float,
        include_legacy_transmission: bool = True,
    ) -> float:
        """估算总时延 = 等待 + 旧配置的数据传输 + 基础执行 + 计算。"""
        wait_time = max(0.0, resource.release_time - current_time)
        transmission_time = (subtask.data_size / max(resource.link_rate, self._epsilon())
                             if include_legacy_transmission else 0.0)
        compute_time = subtask.compute_cycles / max(
            resource.cpu_frequency, self._epsilon()
        )
        base_times = self.defaults.get("task_type_base_time", {})
        execution_time = float(base_times.get(subtask.task_type, 0.0)) + compute_time
        return wait_time + transmission_time + execution_time

    def _energy(self, subtask: SubTask, resource: ResourceNode, latency: float) -> float:
        """估算能耗 = 功率×持续时间 + 与数据量相关的附加能耗。"""
        energy_per_mb = float(self.defaults.get("energy_per_mb", 0.0))
        return resource.power * latency + subtask.data_size * energy_per_mb

    def _is_feasible(
        self,
        subtask: SubTask,
        resource: ResourceNode,
        quality_score: float,
        distance: float,
        latency: float,
        energy: float,
        current_time: float,
    ) -> bool:
        """依次检查状态、占用、能量、时间和资源能力等硬约束。"""
        # 未解除前序依赖的任务不能形成有效 assign 动作。
        if subtask.state != "ready" or current_time < subtask.arrival_time:
            return False
        if not resource.online or resource.occupied:
            return False
        if resource.remaining_energy < energy:
            return False
        if subtask.max_latency > 0 and latency > subtask.max_latency:
            return False
        if self.strict_deadlines and subtask.deadline > 0 and current_time + latency > subtask.deadline:
            return False

        if subtask.task_type in {"detect", "track", "sense"}:
            # 感知任务还必须满足传感器类型、模态、质量和探测范围约束。
            if resource.resource_type != "sensor":
                return False
            if not subtask.required_modalities_any:
                return False
            # A quality threshold of 0 must not turn an unsupported modality
            # into an executable match. Check actual capability compatibility.
            if not set(subtask.required_modalities_any).intersection(resource.modalities):
                return False
            if quality_score < subtask.min_quality:
                return False
            if resource.detection_range > 0 and distance > resource.detection_range:
                return False
            return True

        if resource.resource_type == "compute":
            # 非感知任务在第一阶段统一视为计算任务。
            return resource.cpu_frequency > 0.0

        return False

    def _normalize(self, value: float, max_key: str) -> float:
        """按配置上界做线性归一化；超过上界的值截断为 1。"""
        max_value = float(self.normalization.get(max_key, 1.0))
        return _clamp01(value / max(max_value, self._epsilon()))

    def _epsilon(self) -> float:
        return float(self.normalization.get("epsilon", 1.0e-9))


class MatchMatrixBuilder:
    """遍历所有 SubTask × ResourceNode，生成完整匹配矩阵。"""
    def __init__(self, scorer: RuleBasedScorer):
        self.scorer = scorer

    def build(
        self,
        task_graph: TaskGraph,
        resource_graph: ResourceGraph,
        current_time: float | None = None,
        state: "SchedulingState | None" = None,
    ) -> MatchMatrix:
        if state is None and any(edge.data_size_mb > 0 for edge in task_graph.edges):
            raise ValueError("Explicit data dependencies require SchedulingState for locality checks")
        # 构造矩阵前刷新依赖状态，确保只有当前可执行任务能够 feasible。
        now = resource_graph.timestamp if current_time is None else current_time
        task_graph.update_ready_states(now)
        # entries[i][j] 始终对应 subtask_ids[i] 与 resource_ids[j]。
        entries = [
            [
                self.scorer.score(
                    subtask, resource, current_time=now,
                    transfer=(estimate_data_transfer(state, subtask.subtask_id, resource.resource_id)
                              if state is not None else None),
                )
                for resource in resource_graph.resources
            ]
            for subtask in task_graph.subtasks
        ]
        return MatchMatrix(
            subtask_ids=task_graph.subtask_ids(),
            resource_ids=resource_graph.resource_ids(),
            entries=entries,
        )
