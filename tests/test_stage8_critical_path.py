"""第八阶段：截止时间软约束、关键路径特征、PPO及实验输出。"""
from copy import deepcopy
import math

import pytest

torch = pytest.importorskip('torch')

from ubisched.algorithms.transformer_mappo import (
    CriticalPathTransformerMAPPO, DependencyAwareTransformerMAPPO,
)
from ubisched.experiments.scenarios import make_env
from ubisched.graph.critical_path import build_critical_path_features
from ubisched.scheduling.scheduler_env import RewardConfig


def env(seed=20,pairs=3,scenario='dependency',soft_deadlines=True):
    return make_env(seed,scenario=scenario,pairs=pairs,
                    deadline_features=True,dependency_features=True,
                    critical_path_features=True,soft_deadlines=soft_deadlines,
                    reward_config=RewardConfig(late_fixed_penalty=0.3,late_time_penalty=0.05))


def test_soft_deadline_allows_late_task_and_penalty_once():
    soft=env(20,pairs=1)
    obs,_=soft.reset()
    task=soft.state.get_subtask('detect_0')
    task.deadline=0.1
    obs=soft.observe()
    # The deadline is too close to finish, but the soft-deadline simulator allows dispatch.
    valid=[(agent,i) for agent,o in obs.items()
           for i,mask in enumerate(o['action_mask'][:-1])
           if mask and o['action_labels'][i][0]=='detect_0']
    assert valid
    agent,index=valid[0]
    acts={a:soft.noop_index for a in soft.agents}
    acts[agent]=index
    _,rew0,_,_,info0=soft.step(acts)
    assert 'lateness' not in info0['reward_parts']
    _,rew1,_,_,info1=soft.step({a:soft.noop_index for a in soft.agents})
    assert info1['completed']==['detect_0']
    assert info1['reward_parts']['lateness']<0
    expected=0.3+0.05*(soft.state.assignments[0].actual_end_time-0.1)
    assert -info1['reward_parts']['lateness']==pytest.approx(expected)
    assert info1['deadline_met_rate'] < info1['completion_rate']
    # At any later step this same completed task must not be penalized twice.
    if not (soft._base.terminated or soft._base.truncated):
        _,_,_,_,i2=soft.step({a:soft.noop_index for a in soft.agents})
        assert 'lateness' not in i2['reward_parts']

    hard=env(20,pairs=1,soft_deadlines=False)
    hard.reset()
    hard.state.get_subtask('detect_0').deadline=0.1
    mask=hard.observe()
    assert not any(o['action_mask'][i] for o in mask.values()
                   for i in range(o['noop_index'])
                   if o['action_labels'][i] is not None and o['action_labels'][i][0]=='detect_0')


def test_critical_features_reflect_graph_and_downstream_deadline():
    e=env(21)
    obs,_=e.reset()
    data=obs[e.agents[0]]
    idx={tid:i for i,tid in enumerate(data['task_ids'])}
    # detect_0 has more downstream than classify_0 and a longer remaining path.
    a=idx['detect_0']; b=idx['classify_0']
    assert data['critical_path_features'][a][1] > data['critical_path_features'][b][1]
    assert data['critical_path_features'][a][3] > 0
    before=data['critical_path_features'][a][2]
    e.state.get_subtask('classify_1').deadline -= 3.0
    after=e.observe()[e.agents[0]]['critical_path_features'][a][2]
    assert after <= before + 1e-8
    assert len(data['critical_path_features'])==8
    assert data['critical_path_features'][-1]==[0.0]*6 if len(data['task_ids'])<8 else True


def test_lost_resource_is_visible_in_critical_features():
    e=env(20,pairs=1)
    obs,_=e.reset()
    ids=obs[e.agents[0]]['task_ids']
    i=ids.index('classify_0')
    assert obs[e.agents[0]]['critical_path_features'][i][4]==1.0
    next(r for r in e.state.resource_graph.resources if r.resource_type == 'compute').online=False
    after=e.observe()[e.agents[0]]['critical_path_features'][i]
    assert after[4]==0.0


def test_critical_actor_permutation_and_padding():
    torch.set_num_threads(1)
    torch.manual_seed(13)
    e=env(20,pairs=2)
    o,_=e.reset()
    model=CriticalPathTransformerMAPPO(e,hidden=32,heads=4,layers=1)
    inp=model._make_actor_inputs(e,o)
    perm=torch.tensor([1,0,3,2,4,5,6,7])
    shuffled={k:v.clone() for k,v in inp.items()}
    for key in ('tasks','task_valid','pairs','urgency','dependency_features','critical_path_features'):
        shuffled[key]=shuffled[key][:,perm]
    shuffled['dependency_matrix']=shuffled['dependency_matrix'][:,perm][:,:,perm]
    dirty={k:v.clone() for k,v in inp.items()}
    dirty['critical_path_features'][:,4:,:]=100.0
    with torch.no_grad():
        baseline=model.actor(inp)
        other=model.actor(shuffled)
        padding=model.actor(dirty)
    assert torch.allclose(other[:,:-1].reshape(3,8,1),baseline[:,:-1].reshape(3,8,1)[:,perm],atol=3e-5)
    assert torch.allclose(other[:,-1],baseline[:,-1],atol=3e-5)
    assert torch.allclose(baseline[:,:4],padding[:,:4],atol=3e-5)
    assert torch.allclose(baseline[:,-1],padding[:,-1],atol=3e-5)


def test_critical_actor_ppo_training_and_old_policy_compatibility():
    torch.set_num_threads(1)
    torch.manual_seed(16)
    e=env(22)
    algo=CriticalPathTransformerMAPPO(e,hidden=32,layers=1,heads=4)
    o,_=e.reset()
    features,masks,actions,oldlog=algo.select_actions(e,o)
    with torch.no_grad():
        check=torch.distributions.Categorical(logits=algo.actor(algo._make_actor_inputs(e,o)).masked_fill(~masks,-1e9)).log_prob(actions)
    assert torch.allclose(check,oldlog,atol=1e-5)
    snapshot=[x.detach().clone() for x in algo.actor.parameters()]
    episodes=[algo.sample_episode(env(s)) for s in (20,22)]
    metrics=algo.update(episodes,epochs=1)
    assert all(math.isfinite(x) for x in metrics.values())
    assert any(not torch.equal(x,snapshot[i]) for i,x in enumerate(algo.actor.parameters()))
    old=DependencyAwareTransformerMAPPO(e,hidden=32,layers=1,heads=4)
    old_input=old._make_actor_inputs(e,o)
    basic={k:v for k,v in old_input.items() if k!='critical_path_features'}
    with torch.no_grad():
        assert torch.equal(old.actor(old_input),old.actor(basic))


def test_stage8_cli_exports_consistent_test_cases(tmp_path):
    import sys,csv,json
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
    from run_stage8_critical_path import main
    assert main(['--train-episodes','2','--eval-scenarios','1',
                 '--hidden','32','--heads','4','--layers','1',
                 '--ppo-epochs','1','--output-dir',str(tmp_path)])==0
    progress=json.loads((tmp_path/'progress.json').read_text())
    assert progress['complete']
    assert (tmp_path/'cross_seed_summary.csv').exists()
    assert progress['expected_models']==6
    with (tmp_path/'evaluation_records.csv').open(encoding='utf-8-sig') as f:
        rows=list(csv.DictReader(f))
    for seed in ('11','29','47'):
        a={x['scenario_seed'] for x in rows if x['policy']=='critical_transformer_v8' and x['train_seed']==seed}
        b={x['scenario_seed'] for x in rows if x['policy']=='dependency_transformer_v7_soft' and x['train_seed']==seed}
        assert a==b and len(a)==8
    assert (tmp_path/'critical_transformer_v8_seed_11.pt').exists()
