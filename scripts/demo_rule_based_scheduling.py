from __future__ import annotations

"""从配置开始自动完成整张任务图，不硬编码具体分配动作。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ubisched.graph.match_matrix import RuleBasedScorer
from ubisched.graph.resource_graph import ResourceGraph
from ubisched.graph.task_graph import TaskGraph
from ubisched.scheduling.assignment_executor import AssignmentExecutor
from ubisched.scheduling.rule_based_scheduler import RuleBasedScheduler
from ubisched.scheduling.scheduling_state import SchedulingState


def main() -> None:
    task_graph = TaskGraph.from_yaml(
        ROOT / "configs/ubisched/task_graph_example.yaml"
    )
    resource_graph = ResourceGraph.from_yaml(
        ROOT / "configs/ubisched/resource_graph_example.yaml"
    )
    scorer = RuleBasedScorer.from_yaml(
        ROOT / "configs/ubisched/match_scoring.yaml"
    )
    state = SchedulingState(task_graph, resource_graph)
    scheduler = RuleBasedScheduler(AssignmentExecutor(scorer))

    result = scheduler.run(state)

    print("Rule-based scheduling result")
    print(f"status: {result.status}")
    for index, assignment in enumerate(result.assignments):
        print(
            f"{index}: assign({assignment.subtask_id}, "
            f"{assignment.resource_id}), "
            f"start={assignment.start_time}, "
            f"finish={assignment.completion_time}, "
            f"energy={assignment.estimated_energy}"
        )
    print(f"makespan: {result.makespan}")
    print(f"total_energy: {result.total_energy}")
    print(f"deadline_met_rate: {result.deadline_met_rate}")
    print(f"unfinished_subtasks: {result.unfinished_subtask_ids}")


if __name__ == "__main__":
    main()
