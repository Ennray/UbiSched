from __future__ import annotations

"""演示分配、时间推进、资源释放和后继任务解锁的完整闭环。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ubisched.graph.match_matrix import RuleBasedScorer
from ubisched.graph.resource_graph import ResourceGraph
from ubisched.graph.task_graph import TaskGraph
from ubisched.scheduling.assignment_executor import AssignmentExecutor
from ubisched.scheduling.scheduling_state import SchedulingState


def _print_state(title: str, state: SchedulingState) -> None:
    print(title)
    print(state.summary())
    print(
        "subtasks:",
        {task.subtask_id: task.state for task in state.task_graph.subtasks},
    )
    print(
        "resources:",
        {
            resource.resource_id: {
                "occupied": resource.occupied,
                "release_time": resource.release_time,
                "remaining_energy": resource.remaining_energy,
            }
            for resource in state.resource_graph.resources
        },
    )


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
    executor = AssignmentExecutor(scorer)

    _print_state("Initial state", state)
    print("feasible:", executor.build_match_matrix(state).feasible)
    print()

    first = executor.assign(
        state,
        "detect_target",
        "uav_1_rgb_sensor",
    )
    print(
        f"Assigned detect_target, completion_time={first.completion_time}, "
        f"energy={first.estimated_energy}"
    )
    _print_state("After first assignment", state)
    print()

    executor.advance_to_next_event(state)
    _print_state("After first completion", state)
    print("feasible:", executor.build_match_matrix(state).feasible)
    print()

    second = executor.assign(
        state,
        "classify_target",
        "uav_2_compute",
    )
    print(
        f"Assigned classify_target, completion_time={second.completion_time}, "
        f"energy={second.estimated_energy}"
    )
    executor.advance_to_next_event(state)
    _print_state("Final state", state)
    print("action_mask:", executor.build_action_mask(state).action_mask)


if __name__ == "__main__":
    main()
