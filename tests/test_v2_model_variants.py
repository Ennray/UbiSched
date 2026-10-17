"""只检查两回合更新、保存、加载和推理，不能用于评价算法性能。"""
from dataclasses import asdict

import pytest


def test_all_actor_variants_train_save_and_serve_with_same_contract(tmp_path):
    torch = pytest.importorskip("torch")
    torch.set_num_threads(1)
    from scripts.run_stage11_integrated import main, MODELS
    from ubisched.experiments.integrated_scenario import make_integrated_env
    from ubisched.integration.structured_bridge import ModelPolicy, StructuredAdapter
    from ubisched.config import observation_contract
    assert main(["--train-episodes","2", "--train-seeds","11", "--eval-cases","1",
                 "--batch-size","2", "--ppo-epochs","1", "--hidden","16", "--layers","1",
                 "--models", ",".join(MODELS), "--output-dir",str(tmp_path)]) == 0
    env = make_integrated_env(29); env.reset()
    snapshot = {"version":2, "time":0, "request_uav_id":"UAV1",
                "task_graph":asdict(env.state.task_graph), "resource_graph":asdict(env.state.resource_graph)}
    for model in MODELS:
        path = tmp_path/f"{model}_seed_11.pt"
        weights = torch.load(path, weights_only=True)
        assert weights["observation_contract"] == observation_contract(
            critical_path=model=="mappo_critical_path_transformer")
        result = StructuredAdapter(ModelPolicy(model,path)).decide(snapshot)
        assert result["status"] == "ok" and result["allocations"]
