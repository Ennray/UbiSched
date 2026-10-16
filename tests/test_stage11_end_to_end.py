"""第十一阶段：真实采用通信约束的实验环境及训练/评估入口测试。"""

from copy import deepcopy
from pathlib import Path
import csv
import json

import pytest

from ubisched.experiments.integrated_scenario import (
    NETWORK_CONDITIONS, build_integrated_case, make_integrated_env,
)
from ubisched.experiments.evaluation import choose_rule_actions, run_episode
from ubisched.scheduling.scheduling_state import SchedulingState
from ubisched.scheduling.assignment_executor import AssignmentExecutor


def test_network_variants_share_exact_same_task_graph():
    tasks = [build_integrated_case(19, condition=condition)[0]
             for condition in NETWORK_CONDITIONS]
    assert all(t == tasks[0] for t in tasks)
    assert len(tasks[0].subtasks) == 6
    assert len(tasks[0].edges) == 3
    assert all(edge.data_size_mb > 0 for edge in tasks[0].edges)


def test_fixed_multi_agent_dimensions_and_masks():
    env = make_integrated_env(19)
    obs, _ = env.reset()
    assert env.agents == ("UAV1", "UAV2", "UAV3")
    assert env.action_dim == 8 * 3 + 1
    assert len(env.state_vector()) > len(env.local_vector(obs['UAV1']))
    for agent, local in obs.items():
        assert len(local['action_mask']) == env.action_dim
        assert len(local['task_features']) == 8
        assert len(local['resource_features']) == 3
        assert len(local['dependency_matrix']) == 8
        assert local['action_mask'][-1] == 1
    # 只允许拥有相应资源的 UAV 选择对应任务。
    assert all(pair is None or env.state.get_resource(pair[1]).owner_uav_id == agent
               for agent, local in obs.items() for pair in local['action_labels'])


def test_outage_removes_remote_assignments_from_mask():
    tasks, resources, scorer = build_integrated_case(31, condition='outage')
    state = SchedulingState(tasks, resources)
    executor = AssignmentExecutor(scorer)
    executor.assign(state, 'capture_0', 'cam_0')
    executor.advance_time(state, 1)
    assert not executor.score_assignment(state, 'infer_0', 'cpu_fast_a').feasible
    assert executor.score_assignment(state, 'infer_0', 'cpu_local').feasible
    resources.set_link_online('UAV1', 'UAV2', True)
    assert executor.score_assignment(state, 'infer_0', 'cpu_fast_a').feasible


def test_contention_queues_in_executor_and_changes_match_cost():
    tasks, resources, scorer = build_integrated_case(27, condition='contended')
    state = SchedulingState(tasks, resources)
    executor = AssignmentExecutor(scorer)
    executor.assign(state, 'capture_0', 'cam_0')
    executor.assign(state, 'capture_1', 'cam_1')
    executor.advance_time(state, 1)
    assert {t.subtask_id for t in state.task_graph.ready_subtasks(state.now)} >= {'infer_0','infer_1'}
    before = executor.score_assignment(state, 'infer_1', 'cpu_fast_b').latency_cost
    a = executor.assign(state, 'infer_0', 'cpu_fast_a')
    after = executor.score_assignment(state, 'infer_1', 'cpu_fast_b').latency_cost
    b = executor.assign(state, 'infer_1', 'cpu_fast_b')
    assert after > before
    assert b.communication_queue_wait > 0
    assert b.communication_hops[0].start_time >= a.communication_hops[0].end_time
    assert b.completion_time > a.completion_time
    executor.advance_time(state, max(a.completion_time, b.completion_time))
    assert all(x.status == 'finished' for x in state.transfer_reservations)


def test_rules_query_live_executor_score(monkeypatch):
    env = make_integrated_env(23)
    obs, _ = env.reset()
    calls = []
    old_score = env.executor.score_assignment
    def traced(state, task_id, resource_id):
        calls.append((task_id, resource_id))
        return old_score(state, task_id, resource_id)
    monkeypatch.setattr(env.executor, 'score_assignment', traced)
    actions = choose_rule_actions(env, obs, policy='greedy_score')
    assert calls and set(actions) == set(env.agents)


def test_same_environment_rules_produce_recorded_network_metrics():
    env = make_integrated_env(23, condition='contended')
    metrics = run_episode(env,lambda e,o:choose_rule_actions(e,o,policy='earliest_deadline'),
                          policy='earliest_deadline',scenario='contended',scenario_seed=23)
    assert metrics.total_tasks == 6
    assert metrics.completion_rate == 1.0
    assert sum(a.communication_queue_wait for a in env.state.assignments) > 0
    assert all(h.end_time >= h.start_time for h in env.state.transfer_reservations)
    assert metrics.deadline_met_rate <= metrics.completion_rate


def test_integrated_ppo_checkpoint_and_csv_export(tmp_path):
    torch = pytest.importorskip('torch')
    torch.set_num_threads(1)
    from scripts.run_stage11_integrated import main
    assert main(['--train-episodes','2','--train-seeds','11','--eval-cases','1',
                 '--batch-size','2','--ppo-epochs','1','--hidden','16',
                 '--heads','4','--layers','1', '--output-dir',str(tmp_path)]) == 0
    progress=json.loads((tmp_path/'progress.json').read_text(encoding='utf-8'))
    assert progress['finished'] is True
    assert len(progress['completed_model_runs']) == 2
    for model in ('mappo_mlp','mappo_dependency_transformer'):
        assert (tmp_path/f'{model}_seed_11.pt').is_file()
    with (tmp_path/'evaluation_records.csv').open(encoding='utf-8-sig',newline='') as f:
        records=list(csv.DictReader(f))
    assert len(records) == len(NETWORK_CONDITIONS)*5
    assert all(0 <= float(x['deadline_met_rate']) <= 1 for x in records)
    assert all(x['scenario'] in NETWORK_CONDITIONS for x in records)
    assert all('communication_queue_wait' in x for x in records)
