"""第十阶段：通信资源真正互斥、排队、事件、断链及兼容性。"""
from copy import deepcopy

import pytest

from ubisched.graph.data_transfer import estimate_data_transfer
from ubisched.experiments.link_contention import build_link_contention_case as scenario
from ubisched.scheduling.assignment_executor import AssignmentExecutor
from ubisched.scheduling.scheduling_state import SchedulingState
from ubisched.scheduling.scheduler_env import SchedulerEnv



def ready_state(second_link=False, bandwidth=5.0):
    tasks, resources, scorer = scenario(second_link=second_link, bandwidth=bandwidth)
    state = SchedulingState(tasks, resources)
    exe = AssignmentExecutor(scorer)
    exe.assign(state, "capture_a", "camera")
    exe.advance_to_next_event(state)
    exe.assign(state, "capture_b", "camera")
    exe.advance_to_next_event(state)
    assert state.now == pytest.approx(2)
    return state, exe


def test_same_link_queues_with_distinct_compute_nodes():
    state, exe = ready_state()
    first = exe.assign(state, "infer_a", "cpu_a")
    second = exe.assign(state, "infer_b", "cpu_b")
    assert first.communication_queue_wait == pytest.approx(0)
    assert second.communication_queue_wait == pytest.approx(2)
    assert first.communication_latency == pytest.approx(2)
    assert second.communication_latency == pytest.approx(4)
    a, b = state.transfer_reservations
    assert (a.start_time, a.end_time) == pytest.approx((2, 4))
    assert (b.start_time, b.end_time) == pytest.approx((4, 6))
    assert first.completion_time == pytest.approx(5)
    assert second.completion_time == pytest.approx(7)
    assert second.compute_start_time == pytest.approx(6)
    assert exe.next_communication_event_time(state) == pytest.approx(4)
    # 到达传输结束事件，计算任务尚未完成。
    exe.advance_time(state, 4)
    assert a.status == "finished" and b.status == "transferring"
    assert first.status == "running" and second.status == "running"
    exe.advance_time(state, 5)
    assert first.status == "finished" and second.status == "running"
    exe.advance_time(state, 7)
    assert second.status == "finished"
    assert state.get_resource("cpu_a").occupied is False
    assert state.get_resource("cpu_b").occupied is False


def test_estimation_is_read_only_and_reflects_queue_in_feasibility():
    state, exe = ready_state()
    exe.assign(state, "infer_a", "cpu_a")
    before = deepcopy(state.transfer_reservations)
    transfer = estimate_data_transfer(state, "infer_b", "cpu_b")
    assert transfer.latency == pytest.approx(4)
    assert transfer.queue_wait_s == pytest.approx(2)
    assert state.transfer_reservations == before
    assert exe.score_assignment(state, "infer_b", "cpu_b").latency_cost > 0
    assert len(state.transfer_reservations) == 1


def test_independent_directed_links_allow_parallel_transfer():
    state, exe = ready_state(second_link=True)
    exe.assign(state, "infer_a", "cpu_a")
    second = exe.assign(state, "infer_b", "cpu_b")
    assert second.communication_queue_wait == 0
    assert second.completion_time == pytest.approx(5)
    assert state.transfer_reservations[0].start_time == state.transfer_reservations[1].start_time


def test_link_failure_cancels_transfers_and_retries_tasks():
    state, exe = ready_state()
    first = exe.assign(state, "infer_a", "cpu_a")
    second = exe.assign(state, "infer_b", "cpu_b")
    exe.advance_time(state, 3)
    interrupted = exe.set_link_online(state, "uav1", "uav2", False)
    assert {item.subtask_id for item in interrupted} == {"infer_a", "infer_b"}
    assert first.status == "failed" and second.status == "failed"
    assert not state.get_resource("cpu_a").occupied
    assert not state.get_resource("cpu_b").occupied
    assert {r.status for r in state.transfer_reservations} == {"cancelled"}
    assert state.get_subtask("infer_a").state == "ready"
    assert not exe.score_assignment(state, "infer_a", "cpu_a").feasible
    exe.set_link_online(state, "uav1", "uav2", True)
    fresh = exe.assign(state, "infer_a", "cpu_a")
    assert fresh.communication_queue_wait == 0
    assert fresh.communication_hops[0].start_time == pytest.approx(3)


def test_failure_after_transfer_does_not_cancel_compute():
    state, exe = ready_state()
    assigned = exe.assign(state, "infer_a", "cpu_a")
    exe.advance_time(state, 4.5)
    assert state.transfer_reservations[0].status == "finished"
    interrupted = exe.set_link_online(state, "uav1", "uav2", False)
    assert interrupted == [] and assigned.status == "running"
    exe.advance_time(state, 5)
    assert assigned.status == "finished"


def test_resource_failure_cancels_its_future_reservations():
    state, exe = ready_state()
    exe.assign(state, "infer_a", "cpu_a")
    exe.assign(state, "infer_b", "cpu_b")
    exe.fail_resource(state, "cpu_a")
    assert state.transfer_reservations[0].status == "cancelled"
    # 第二个任务保持已有预约；新的任务可以填补取消后的前面空档。
    assert not exe.score_assignment(state, "infer_a", "cpu_a").feasible
    exe.restore_resource(state, "cpu_a")
    new_estimate = estimate_data_transfer(state, "infer_a", "cpu_a")
    assert new_estimate.hops[0].start_time == pytest.approx(2)
    assert new_estimate.hops[0].end_time == pytest.approx(4)


def test_soft_deadline_can_reject_when_queue_exceeds_max_latency():
    state, exe = ready_state()
    exe.assign(state, "infer_a", "cpu_a")
    state.get_subtask("infer_b").max_latency = 3
    assert not exe.score_assignment(state, "infer_b", "cpu_b").feasible
    with pytest.raises(ValueError):
        exe.assign(state, "infer_b", "cpu_b")


def test_reset_clears_reservation_history():
    tasks, resources, scorer = scenario()
    env = SchedulerEnv(tasks, resources, scorer)
    obs, _ = env.reset()
    env.executor.assign(env.state, "capture_a", "camera")
    env.executor.advance_to_next_event(env.state)
    env.executor.assign(env.state, "capture_b", "camera")
    env.executor.advance_to_next_event(env.state)
    env.executor.assign(env.state, "infer_a", "cpu_a")
    assert len(env.state.transfer_reservations) == 1
    env.reset()
    assert env.state.transfer_reservations == []


def test_link_failure_after_hop_completes_only_interrupts_pending_ones():
    state, exe = ready_state(second_link=True)
    a = exe.assign(state, "infer_a", "cpu_a")
    b = exe.assign(state, "infer_b", "cpu_b")
    exe.advance_time(state, 3)
    result = exe.set_link_online(state, "uav1", "uav2", False)
    assert [item.subtask_id for item in result] == ["infer_a"]
    assert a.status == "failed" and b.status == "running"
    exe.advance_time(state, 5)
    assert b.status == "finished"


def test_failure_during_second_transfer_preserves_first_compute():
    state, exe = ready_state()
    first = exe.assign(state, "infer_a", "cpu_a")
    second = exe.assign(state, "infer_b", "cpu_b")
    exe.advance_time(state, 4.5)  # 第一份数据已传完，第二份正在传
    interrupted = exe.set_link_online(state, "uav1", "uav2", False)
    assert [item.subtask_id for item in interrupted] == ["infer_b"]
    assert first.status == "running" and second.status == "failed"
    exe.advance_time(state, 5)
    assert first.status == "finished"


def test_two_inputs_for_one_task_are_queued_sequentially():
    state, exe = ready_state()
    state.task_graph.edges.append(type(state.task_graph.edges[0])(
        src_subtask_id="capture_b", dst_subtask_id="infer_a", data_size_mb=10
    ))
    transfer = estimate_data_transfer(state, "infer_a", "cpu_a")
    assert len(transfer.hops) == 2
    assert [(h.start_time, h.end_time) for h in transfer.hops] == pytest.approx([(2, 4), (4, 6)])
    assert transfer.queue_wait_s == 0
    record = exe.assign(state, "infer_a", "cpu_a")
    assert record.communication_latency == pytest.approx(4)
    assert record.completion_time == pytest.approx(7)


def test_queued_network_cost_is_exposed_in_matching_matrix():
    state, exe = ready_state()
    before = exe.build_match_matrix(state)
    col = before.resource_ids.index("cpu_b")
    row = before.subtask_ids.index("infer_b")
    no_queue = before.entries[row][col].latency_cost
    exe.assign(state, "infer_a", "cpu_a")
    after = exe.build_match_matrix(state)
    with_queue = after.entries[row][col].latency_cost
    assert with_queue > no_queue
