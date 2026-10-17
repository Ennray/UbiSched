"""新版训练、推理、执行共用的数据约定。修改后应重新训练模型。"""
from copy import deepcopy
import hashlib
import json

SCHEMA_VERSION = "ubisched-2.1"
CAPACITIES = {"max_tasks": 8, "max_resources_per_uav": 3, "max_agents": 3}
SCORING = {
    "strict_deadlines": False,
    "normalization": {"max_latency": 40, "max_energy": 500,
                      "max_cpu_frequency": 10, "max_queue_length": 10,
                      "max_distance": 100, "max_priority": 10},
    "defaults": {"task_type_base_time": {"sense": 1.0, "detect": 1.0,
                                          "track": 1.0, "classify": 0.0}},
    "match_weights": {"quality": 0.38, "latency": 0.52,
                      "energy": 0.06, "priority": 0.04},
}
UNITS = {"time": "s since mission start", "data": "MB",
         "compute_cycles": "Gcycle", "cpu_frequency": "GHz",
         "power": "W", "energy": "J", "location": "m"}


def observation_contract(*, critical_path=False):
    # Feature order is part of the contract, not just the tensor dimensions.
    return {"schema": SCHEMA_VERSION, "capacities": deepcopy(CAPACITIES),
            "units": deepcopy(UNITS), "scoring": deepcopy(SCORING),
            "features": {"task": 16, "resource": 14, "pair": 7,
                         "dependency": 4, "deadline": True,
                         "critical_path": bool(critical_path),
                         "feature_order": "scheduler_env.observe:v1",
                         "energy_scale": "mission initial max(1, remaining_energy); snapshot.energy_normalization",
                         "urgency_scale_s": 20, "dependency_slack_scale_s": 60},
            "actions": {"coordinate_actions": True, "work_conserving": True}}


def contract_hash(contract):
    raw = json.dumps(contract, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def make_scorer():
    from ubisched.graph.match_matrix import RuleBasedScorer
    return RuleBasedScorer(deepcopy(SCORING))


def make_env(tasks, resources, *, critical_path=False, max_steps=90):
    from ubisched.scheduling.multi_agent_env import MultiAgentSchedulerEnv
    from ubisched.scheduling.scheduler_env import RewardConfig
    return MultiAgentSchedulerEnv(
        tasks, resources, make_scorer(), **CAPACITIES, max_steps=max_steps,
        include_deadline_features=True, include_dependency_features=True,
        include_critical_path_features=critical_path,
        reward_config=RewardConfig(late_fixed_penalty=0.3, late_time_penalty=0.05))
