"""同任务分别测试高速、低速与断链，看是否改变执行位置。"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ubisched.experiments.sensing_compute import build_sensing_compute_case
from ubisched.scheduling.assignment_executor import AssignmentExecutor
from ubisched.scheduling.rule_based_scheduler import RuleBasedScheduler
from ubisched.scheduling.scheduling_state import SchedulingState


def run_case(name, bandwidth, online):
    task_graph, resource_graph, scorer = build_sensing_compute_case(bandwidth, online)
    state = SchedulingState(task_graph, resource_graph)
    result = RuleBasedScheduler(AssignmentExecutor(scorer)).run(state)
    recognition = next((a for a in result.assignments if a.subtask_id == "infer"), None)
    return {
        "case": name, "status": result.status,
        "compute_resource": recognition.resource_id if recognition else "none",
        "makespan_s": round(result.makespan, 4),
        "communication_latency_s": round(recognition.communication_latency, 4) if recognition else 0,
        "communication_energy": round(recognition.communication_energy, 4) if recognition else 0,
        "total_energy": round(result.total_energy, 4),
        "deadline_met_rate": round(result.deadline_met_rate, 4),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="outputs/stage9/sensing_compute_demo.csv")
    args = parser.parse_args()
    cases = [run_case("fast_link", 5, True),
             run_case("slow_link", 0.5, True),
             run_case("offline_link", 5, False)]
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(cases[0]))
        writer.writeheader()
        writer.writerows(cases)
    for case in cases:
        print(case)
    print(f"CSV saved: {out}")


if __name__ == "__main__":
    main()
