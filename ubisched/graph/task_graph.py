from __future__ import annotations

"""任务图的数据模型。

定义复杂任务的图结构。一个完整任务不再被看成一个单独 ID，而是被拆分成多个可单独调度的子任务。
每个子任务用 SubTask 表示，子任务之间的先后依赖用 TaskEdge 表示。
TaskGraph 负责保存这些子任务和依赖关系，并根据前序任务是否完成，自动判断哪些 pending 子任务可以变成 ready。

"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence


def _load_structured_file(path: str | Path) -> Dict[str, Any]:
    """读取 YAML 配置；未安装 PyYAML 时兼容 JSON 格式的 YAML 文件。配置文件结果类似：
    task_graph_id: mission_001
    subtasks: []
    edges: []
    """
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
class SubTask:
    """可被单独调度的任务节点。

    时间、数据量、计算量等数值的单位由场景配置统一约定。匹配器只要求
    TaskGraph、ResourceGraph 和评分配置使用相同单位。
    """
    subtask_id: str
    task_type: str
    priority: float
    deadline: float
    location: List[float]
    required_modalities_any: List[str]
    min_quality: float
    data_size: float
    compute_cycles: float
    max_latency: float
    resource_count_min: int
    resource_count_max: int
    state: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubTask":
        """把配置字典转换成强类型节点，并为非必填字段提供默认值。"""
        return cls(
            subtask_id=str(data["subtask_id"]),
            task_type=str(data["task_type"]),
            priority=float(data.get("priority", 0.0)),
            deadline=float(data.get("deadline", 0.0)),
            location=[float(v) for v in data.get("location", [0.0, 0.0, 0.0])],
            required_modalities_any=[
                str(v) for v in data.get("required_modalities_any", [])
            ],
            min_quality=float(data.get("min_quality", 0.0)),
            data_size=float(data.get("data_size", 0.0)),
            compute_cycles=float(data.get("compute_cycles", 0.0)),
            max_latency=float(data.get("max_latency", 0.0)),
            resource_count_min=int(data.get("resource_count_min", 1)),
            resource_count_max=int(data.get("resource_count_max", 1)),
            state=str(data.get("state", "pending")),
        )


@dataclass
class TaskEdge:
    """任务依赖边：src 完成后，dst 才可能进入 ready 状态。"""
    src_subtask_id: str
    dst_subtask_id: str
    edge_type: str = "precedence"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskEdge":
        # 第一阶段刻意限制为 precedence，避免把数据流等语义混入当前模型。
        edge_type = str(data.get("edge_type", "precedence"))
        if edge_type != "precedence":
            raise ValueError(f"Unsupported task edge type: {edge_type}")
        return cls(
            src_subtask_id=str(data["src_subtask_id"]),
            dst_subtask_id=str(data["dst_subtask_id"]),
            edge_type=edge_type,
        )


@dataclass
class TaskGraph:
    """保存一项复杂任务的所有子任务及其前序依赖。"""
    task_graph_id: str
    subtasks: List[SubTask]
    edges: List[TaskEdge]
    created_time: float = 0.0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskGraph":
        return cls(
            task_graph_id=str(data["task_graph_id"]),
            created_time=float(data.get("created_time", 0.0)),
            subtasks=[SubTask.from_dict(item) for item in data.get("subtasks", [])],
            edges=[TaskEdge.from_dict(item) for item in data.get("edges", [])],
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> "TaskGraph":
        return cls.from_dict(_load_structured_file(path))

    def subtask_ids(self) -> List[str]:
        return [subtask.subtask_id for subtask in self.subtasks]

    def get_subtask(self, subtask_id: str) -> SubTask:
        for subtask in self.subtasks:
            if subtask.subtask_id == subtask_id:
                return subtask
        raise KeyError(f"Unknown subtask_id: {subtask_id}")

    def update_ready_states(self) -> None:
        """根据前序完成情况，把满足条件的 pending 节点推进为 ready。

        没有前序节点的 pending 子任务会直接 ready；running、finished 等
        非 pending 状态不会被本方法覆盖。
        """
        finished = {
            subtask.subtask_id for subtask in self.subtasks if subtask.state == "finished"
        }
        predecessors: Dict[str, List[str]] = {
            subtask.subtask_id: [] for subtask in self.subtasks
        }
        for edge in self.edges:
            predecessors.setdefault(edge.dst_subtask_id, []).append(edge.src_subtask_id)

        # 一个节点的全部直接前序都 finished，才允许进入候选匹配集合。
        for subtask in self.subtasks:
            if subtask.state != "pending":
                continue
            if all(src_id in finished for src_id in predecessors.get(subtask.subtask_id, [])):
                subtask.state = "ready"

    def ready_subtasks(self) -> List[SubTask]:
        self.update_ready_states()
        return [subtask for subtask in self.subtasks if subtask.state == "ready"]

    def summary(self) -> str:
        state_counts: Dict[str, int] = {}
        for subtask in self.subtasks:
            state_counts[subtask.state] = state_counts.get(subtask.state, 0) + 1
        return (
            f"TaskGraph(id={self.task_graph_id}, "
            f"subtasks={len(self.subtasks)}, edges={len(self.edges)}, "
            f"states={state_counts})"
        )


def build_precedence_matrix(task_graph: TaskGraph) -> List[List[int]]:
    """构造任务邻接矩阵；matrix[i][j] == 1 表示 i 必须先于 j。"""
    ids = task_graph.subtask_ids()
    index = {subtask_id: i for i, subtask_id in enumerate(ids)}
    matrix = [[0 for _ in ids] for _ in ids]
    for edge in task_graph.edges:
        matrix[index[edge.src_subtask_id]][index[edge.dst_subtask_id]] = 1
    return matrix


def validate_location(location: Sequence[float]) -> None:
    if len(location) not in (2, 3):
        raise ValueError("location must be 2D or 3D")
