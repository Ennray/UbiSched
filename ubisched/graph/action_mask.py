from __future__ import annotations

"""把 MatchMatrix 的可行性结果转换成离散动作掩码。"""

from dataclasses import dataclass
from typing import List

from ubisched.graph.match_matrix import MatchMatrix


@dataclass
class ActionMask:
    """action_mask 与 action_labels 使用完全相同的索引。"""
    action_mask: List[int]
    action_labels: List[str]

    @property
    def noop_index(self) -> int:
        return len(self.action_mask) - 1


class ActionMaskBuilder:
    """按任务优先、资源次序将二维 feasible 矩阵展平成一维动作。"""

    def build(self, match_matrix: MatchMatrix, include_noop: bool = True) -> ActionMask:
        mask: List[int] = []
        labels: List[str] = []
        # 行优先展开：(task0,res0), (task0,res1), (task1,res0), ...
        for subtask_id, row in zip(match_matrix.subtask_ids, match_matrix.entries):
            for resource_id, entry in zip(match_matrix.resource_ids, row):
                mask.append(1 if entry.feasible else 0)
                labels.append(f"assign({subtask_id}, {resource_id})")

        if include_noop:
            # noop 始终可用，保证即使没有可行分配，动作集合也不为空。
            mask.append(1)
            labels.append("noop")

        return ActionMask(action_mask=mask, action_labels=labels)
