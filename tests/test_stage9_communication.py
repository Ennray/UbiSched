"""第九阶段：前序数据位置、链路代价、资源一致性及 MAPPO 观测。"""
from copy import deepcopy
import pytest

from ubisched.graph.task_graph import TaskEdge, TaskGraph, SubTask
from ubisched.graph.resource_graph import ResourceGraph, CommunicationLink
from ubisched.graph.match_matrix import RuleBasedScorer
from ubisched.scheduling.scheduling_state import SchedulingState
from ubisched.scheduling.assignment_executor import AssignmentExecutor
from ubisched.scheduling.multi_agent_env import MultiAgentSchedulerEnv


def fixture(bandwidth=5.0, online=True, source_energy=200, edge_size=10.0):
    task = TaskGraph.from_dict({
        "task_graph_id":"stage9", "subtasks":[
            {"subtask_id":"capture", "task_type":"sense", "priority":10,
             "required_modalities_any":["rgb"], "min_quality":0.5,
             "deadline":100, "max_latency":20},
            {"subtask_id":"infer", "task_type":"classify", "priority":10,
             "compute_cycles":10, "deadline":100, "max_latency":10},
        ], "edges":[{"src_subtask_id":"capture", "dst_subtask_id":"infer",
                     "data_size_mb":edge_size}]
    })
    resources=ResourceGraph.from_dict({
        "resource_graph_id":"stage9", "resources":[
            {"resource_id":"camera", "owner_uav_id":"uav1", "resource_type":"sensor",
             "modalities":["rgb"], "sensing_quality":{"rgb":0.9},
             "remaining_energy":source_energy, "power":1, "link_rate":10},
            {"resource_id":"local_cpu", "owner_uav_id":"uav1", "resource_type":"compute",
             "cpu_frequency":2, "remaining_energy":100, "power":1},
            {"resource_id":"remote_cpu", "owner_uav_id":"uav2", "resource_type":"compute",
             "cpu_frequency":10, "remaining_energy":100, "power":1},
        ],"communication_links":[{"source_uav_id":"uav1", "target_uav_id":"uav2",
             "bandwidth_mb_s":bandwidth, "latency_s":0.2,
             "energy_per_mb":0.2, "online":online}]
    })
    scorer=RuleBasedScorer({
        "strict_deadlines":False,
        "normalization":{"max_latency":100, "max_energy":1000,
                         "max_distance":100, "max_cpu_frequency":10,
                         "max_priority":10, "max_queue_length":10},
        "match_weights":{"quality":0.5,"latency":0.5},
        "defaults":{"task_type_base_time":{"sense":1, "classify":0}}})
    return task, resources, scorer


def finish_capture(state, executor):
    record=executor.assign(state,"capture","camera")
    executor.advance_to_next_event(state)
    assert record.status=="finished"
    assert state.get_subtask("infer").state=="ready"


def test_explicit_edge_data_and_validation():
    edge=TaskEdge.from_dict({"src_subtask_id":"a", "dst_subtask_id":"b", "data_size_mb":10})
    assert edge.data_size_mb==10
    assert TaskEdge.from_dict({"src_subtask_id":"a","dst_subtask_id":"b"}).data_size_mb==0
    with pytest.raises(ValueError):
        TaskEdge.from_dict({"src_subtask_id":"a","dst_subtask_id":"b","data_size_mb":-1})
    with pytest.raises(ValueError):
        CommunicationLink("uav1","uav2",0)


def test_local_and_remote_assignment_have_distinct_costs():
    tasks, resources, scorer=fixture()
    state=SchedulingState(tasks, resources)
    executor=AssignmentExecutor(scorer)
    finish_capture(state,executor)
    matrix=executor.build_match_matrix(state)
    i=matrix.subtask_ids.index("infer")
    l=matrix.resource_ids.index("local_cpu")
    r=matrix.resource_ids.index("remote_cpu")
    assert matrix.entries[i][l].feasible and matrix.entries[i][r].feasible
    assert matrix.entries[i][r].latency_cost < matrix.entries[i][l].latency_cost
    assert matrix.entries[i][r].match_score > matrix.entries[i][l].match_score
    remote=executor.assign(state,"infer","remote_cpu")
    assert remote.communication_latency==pytest.approx(2.2)
    assert remote.communication_energy==pytest.approx(2)
    assert remote.estimated_latency==pytest.approx(3.2)
    assert remote.estimated_energy==pytest.approx(3)
    assert state.get_resource("camera").remaining_energy==pytest.approx(197)
    assert state.get_resource("remote_cpu").remaining_energy==pytest.approx(99)
    assert remote.communication_hops[0].source_uav_id=="uav1"
    executor.advance_to_next_event(state)
    assert state.now==pytest.approx(4.2)
    assert state.get_subtask("infer").state=="finished"


def test_low_bandwidth_and_offline_link_mask_remote_but_not_local():
    for speed,online in ((0.5,True),(5,False)):
        tasks,resources,scorer=fixture(bandwidth=speed,online=online)
        state=SchedulingState(tasks,resources)
        exe=AssignmentExecutor(scorer)
        finish_capture(state,exe)
        assert exe.score_assignment(state,"infer","local_cpu").feasible
        assert not exe.score_assignment(state,"infer","remote_cpu").feasible
        with pytest.raises(ValueError):
            exe.assign(state,"infer","remote_cpu")
        assert not state.get_resource("remote_cpu").occupied
        exe.assign(state,"infer","local_cpu")


def test_no_link_does_not_silently_use_fallback_link_rate():
    tasks, resources, scorer=fixture()
    resources.communication_links=[]
    state=SchedulingState(tasks,resources)
    executor=AssignmentExecutor(scorer)
    finish_capture(state,executor)
    assert not executor.score_assignment(state,"infer","remote_cpu").feasible


def test_sender_energy_limits_cross_uav_data_transfer():
    tasks,resources,scorer=fixture(source_energy=2.5)
    state=SchedulingState(tasks,resources)
    executor=AssignmentExecutor(scorer)
    finish_capture(state,executor)  # 采集耗能1，发送需2，只剩1.5
    assert not executor.score_assignment(state,"infer","remote_cpu").feasible
    assert executor.score_assignment(state,"infer","local_cpu").feasible


def test_legacy_without_data_edges_needs_no_network_config():
    tasks,resources,scorer=fixture(edge_size=0)
    resources.communication_links=[]
    state=SchedulingState(tasks,resources)
    exe=AssignmentExecutor(scorer)
    finish_capture(state,exe)
    assert exe.score_assignment(state,"infer","remote_cpu").feasible
    record=exe.assign(state,"infer","remote_cpu")
    assert record.communication_latency==0
    assert record.communication_energy==0


def test_multiagent_mask_and_reward_use_same_communication_cost():
    tasks,resources,scorer=fixture()
    env=MultiAgentSchedulerEnv(tasks,resources,scorer,
        max_tasks=3, max_resources_per_uav=2, max_agents=2)
    obs,_=env.reset()
    actions={a:env.noop_index for a in env.agents}
    actions["uav1"]=obs["uav1"]["action_labels"].index(("capture","camera"))
    obs,_,_,_,info=env.step(actions)
    obs,_,_,_,info=env.step({a:env.noop_index for a in env.agents})
    action=obs["uav2"]["action_labels"].index(("infer","remote_cpu"))
    assert obs["uav2"]["action_mask"][action]==1
    acts={a:env.noop_index for a in env.agents}
    acts["uav2"]=action
    obs,reward,_,_,info=env.step(acts)
    assert info["started"]==[("infer","remote_cpu")]
    assert env.state.assignments[-1].communication_latency==pytest.approx(2.2)
    assert info["reward_parts"]["energy"]==pytest.approx(-env._base.rewards.energy_cost*3/1000)


def test_reset_recovers_link_state_and_energy():
    tasks,resources,scorer=fixture()
    env=MultiAgentSchedulerEnv(tasks,resources,scorer, max_tasks=3,
                              max_resources_per_uav=2,max_agents=2)
    env.reset()
    env.state.resource_graph.communication_links[0].online=False
    env.state.get_resource("camera").remaining_energy=0
    env.reset()
    assert env.state.resource_graph.communication_links[0].online
    assert env.state.get_resource("camera").remaining_energy==200


def test_runtime_added_dependency_edges_store_data_sizes_and_validate():
    tasks,resources,scorer=fixture()
    state=SchedulingState(tasks,resources)
    incoming=deepcopy(state.get_subtask("infer"))
    incoming.subtask_id="followup"
    incoming.state="pending"
    state.add_subtask(incoming, predecessors=["capture"],
                      predecessor_data_sizes={"capture":8.0})
    edge=next(e for e in state.task_graph.edges if e.dst_subtask_id=="followup")
    assert edge.data_size_mb==8
    before=len(state.task_graph.subtasks)
    bad=deepcopy(incoming)
    bad.subtask_id="bad"
    with pytest.raises(ValueError):
        state.add_subtask(bad, predecessors=["capture"],
                          predecessor_data_sizes={"missing":1})
    assert len(state.task_graph.subtasks)==before


def test_standalone_matrix_builder_rejects_missing_transfer_context():
    from ubisched.graph.match_matrix import MatchMatrixBuilder
    tasks,resources,scorer=fixture()
    with pytest.raises(ValueError, match="SchedulingState"):
        MatchMatrixBuilder(scorer).build(tasks, resources)


def test_runtime_link_failure_and_recovery_changes_agent_mask():
    tasks,resources,scorer=fixture()
    env=MultiAgentSchedulerEnv(tasks,resources,scorer,
         max_tasks=3,max_resources_per_uav=2,max_agents=2)
    obs,_=env.reset()
    a={uav:env.noop_index for uav in env.agents}
    a["uav1"]=obs["uav1"]["action_labels"].index(("capture","camera"))
    env.step(a)
    obs,_,_,_,_=env.step({uav:env.noop_index for uav in env.agents})
    idx=obs["uav2"]["action_labels"].index(("infer","remote_cpu"))
    assert obs["uav2"]["action_mask"][idx]==1
    env.set_link_online("uav1","uav2",False)
    assert env.observe()["uav2"]["action_mask"][idx]==0
    env.set_link_online("uav1","uav2",True)
    assert env.observe()["uav2"]["action_mask"][idx]==1
