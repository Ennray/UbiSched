"""第十阶段演示：两个依赖任务竞争同一条链路，验证排队真实影响完工时间。"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ubisched.experiments.link_contention import build_link_contention_case
from ubisched.scheduling.scheduling_state import SchedulingState
from ubisched.scheduling.assignment_executor import AssignmentExecutor


def run_case(name: str, parallel_links: bool) -> list[dict]:
    tasks, resources, scorer = build_link_contention_case(second_link=parallel_links)
    state = SchedulingState(tasks, resources)
    executor = AssignmentExecutor(scorer)
    for name_capture in ("capture_a", "capture_b"):
        executor.assign(state, name_capture, "camera")
        executor.advance_to_next_event(state)
    first = executor.assign(state, "infer_a", "cpu_a")
    second = executor.assign(state, "infer_b", "cpu_b")
    assert len(state.transfer_reservations) == 2
    events = []
    while executor.next_event_time(state) is not None:
        executor.advance_to_next_event(state)
        events.append(state.now)
    assert first.status == second.status == "finished"
    return [
        {
            "case": name,
            "task": item.subtask_id,
            "compute_resource": item.resource_id,
            "link": f"{hop.source_uav_id}->{hop.target_uav_id}",
            "transfer_start_s": hop.start_time,
            "transfer_end_s": hop.end_time,
            "queue_wait_s": item.communication_queue_wait,
            "compute_start_s": item.compute_start_time,
            "task_finished_s": item.actual_end_time,
            "status": item.status,
        }
        for item in (first, second)
        for hop in item.communication_hops
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='outputs/stage10/communication_contention.csv')
    args = parser.parse_args()
    rows = run_case('shared_link', False) + run_case('independent_links', True)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for r in rows:
        print(f"{r['case']:<20} {r['task']:<10} {r['link']:<12} "
              f"transfer {r['transfer_start_s']:.1f}~{r['transfer_end_s']:.1f}s  "
              f"wait={r['queue_wait_s']:.1f}s finished={r['task_finished_s']:.1f}s")
    print(f'Saved: {out}')

if __name__ == '__main__':
    main()
