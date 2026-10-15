"""第一阶段示例：运行中资源故障、备用资源接替、未来任务到达。"""
from __future__ import annotations

import sys
from copy import deepcopy
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
    state = SchedulingState(
        TaskGraph.from_yaml(ROOT / "configs/ubisched/task_graph_example.yaml"),
        ResourceGraph.from_yaml(ROOT / "configs/ubisched/resource_graph_example.yaml"),
    )
    scorer = RuleBasedScorer.from_yaml(ROOT / "configs/ubisched/match_scoring.yaml")
    executor = AssignmentExecutor(scorer)

    # 第二架 UAV 的备用传感器，演示发生故障后重新选择资源。
    backup = deepcopy(state.get_resource("uav_1_rgb_sensor"))
    backup.resource_id = "uav_3_rgb_sensor"
    backup.owner_uav_id = "uav_3"
    backup.sensing_quality = {"rgb": 0.82, "infrared": 0.76}
    state.resource_graph.resources.append(backup)

    print("[0.00s] 分配首个任务给 UAV1")
    attempt = executor.assign(state, "detect_target", "uav_1_rgb_sensor")
    executor.advance_time(state, 2.0)
    failed = executor.fail_resource(state, "uav_1_rgb_sensor")
    print(f"[2.00s] UAV1传感器掉线，中断 {len(failed)} 个任务，等待重分配")

    # 后续任务在 12 秒到达；即使系统提前空闲，也不能提前运行。
    incoming = deepcopy(state.get_subtask("detect_target"))
    incoming.subtask_id = "recheck_target"
    incoming.arrival_time = 12.0
    incoming.deadline = 90.0
    state.add_subtask(incoming, predecessors=["classify_target"])
    print("[2.00s] 注入新任务，指定12秒才到达，并依赖目标分类完成")

    result = RuleBasedScheduler(executor).run(state)
    for assignment in state.assignments:
        print(
            f"[{assignment.start_time:.2f}s] {assignment.subtask_id} -> "
            f"{assignment.resource_id}; status={assignment.status}; "
            f"planned_end={assignment.completion_time:.2f}s"
        )
    print(f"运行结果: {result.status}; 当前时间: {state.now:.2f}s")
    print("任务状态:", {x.subtask_id: x.state for x in state.task_graph.subtasks})
    print("说明：这是估算时延驱动的离散事件仿真，不代表 AirSim 真实执行反馈。")


if __name__ == "__main__":
    main()
