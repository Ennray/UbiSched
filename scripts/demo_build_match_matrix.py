from __future__ import annotations

"""从示例配置构建任务图、资源图、匹配矩阵和动作掩码。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# 允许直接执行本脚本时导入仓库根目录下的 ubisched 包。
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ubisched.graph.action_mask import ActionMaskBuilder
from ubisched.graph.match_matrix import MatchMatrixBuilder, RuleBasedScorer
from ubisched.graph.resource_graph import ResourceGraph
from ubisched.graph.task_graph import TaskGraph


def _print_matrix(title: str, matrix: list[list[float | int]]) -> None:
    print(title)
    for row in matrix:
        print(row)


def main() -> None:
    # 1. 配置数据进入两个图模型。
    task_graph = TaskGraph.from_yaml(ROOT / "configs/ubisched/task_graph_example.yaml")
    resource_graph = ResourceGraph.from_yaml(
        ROOT / "configs/ubisched/resource_graph_example.yaml"
    )
    scorer = RuleBasedScorer.from_yaml(ROOT / "configs/ubisched/match_scoring.yaml")
    # 2. 对每个任务-资源组合评分，再仅依据 feasible 生成动作掩码。
    match_matrix = MatchMatrixBuilder(scorer).build(task_graph, resource_graph)
    action_mask = ActionMaskBuilder().build(match_matrix)

    print("TaskGraph summary")
    print(task_graph.summary())
    print()
    print("ResourceGraph summary")
    print(resource_graph.summary())
    print()
    _print_matrix("feasible matrix", match_matrix.feasible)
    print()
    _print_matrix("match_score matrix", match_matrix.match_score)
    print()
    print("action_mask")
    print(action_mask.action_mask)


if __name__ == "__main__":
    main()
