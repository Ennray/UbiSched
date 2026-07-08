# MAPPO 训练流程说明

本文档说明 `F:\工作\173\代码\i-ssros` 项目中 MAPPO 训练代码的真实入口、训练数据流、训练产物位置，以及从零训练到 C++ 推理使用权重的完整步骤。

## 1. 训练代码位置

MAPPO 训练代码位于：

```text
light_mappo-transformer/light_mappo-main/
```

主要文件如下：

| 文件 | 作用 |
| --- | --- |
| `train/train.py` | 当前实际训练入口。 |
| `config.py` | 训练超参数、环境参数、保存参数配置。 |
| `envs/env_core.py` | 自定义任务环境核心逻辑。 |
| `envs/env_discrete.py` | 将自定义环境封装成 MAPPO 可用的 MultiDiscrete 环境。 |
| `envs/env_wrappers.py` | 多环境并行采样封装 `DummyVecEnv`。 |
| `runner/separated/env_runner.py` | 非共享策略训练循环。当前默认走这里。 |
| `runner/separated/base_runner.py` | 初始化 policy、trainer、buffer，保存和恢复模型。 |
| `algorithms/algorithm/rMAPPOPolicy.py` | actor/critic 策略封装。 |
| `algorithms/algorithm/r_mappo.py` | PPO 更新逻辑。 |
| `train/new.py` | 推理入口，不是训练入口。C++ 选择插件调用这个文件。 |
| `weights/` | 推理使用的预训练 actor 权重目录。 |

注意：`scripts/train_mpe.sh` 是旧的 MPE 训练脚本，里面调用的是 `train/train_mpe.py`，但当前项目没有这个文件。因此当前项目训练不要从 `scripts/train_mpe.sh` 开始，应直接使用 `train/train.py`。

## 2. 环境依赖

训练脚本直接依赖以下 Python 包：

```text
torch
numpy
gym
tensorboardX
setproctitle
matplotlib
pandas
sympy
tornado
absl-py
```

在当前机器上我检查到：

```text
torch: 已安装
numpy: 已安装
matplotlib: 已安装
pandas: 已安装
sympy: 已安装
tornado: 已安装
gym: 未安装
tensorboardX: 未安装
setproctitle: 未安装
absl-py: 未安装
```

因此在当前环境下，原始训练脚本不能直接跑通。至少需要先安装缺失依赖：

```bash
pip install gym tensorboardX setproctitle absl-py
```

如果使用 Linux/虚拟环境，建议先进入项目使用的 Python 环境，再安装：

```bash
cd /path/to/i-ssros/light_mappo-transformer/light_mappo-main
python -m pip install gym tensorboardX setproctitle absl-py
```

## 3. 当前训练任务定义

当前训练不是标准 MPE 环境，而是项目自定义的无人机任务分配环境。

核心环境在：

```text
envs/env_core.py
```

关键参数：

```python
self.agent_num = 2
self.obs_dim = 15
self.action_dim = [5, 4]
```

含义：

| 参数 | 含义 |
| --- | --- |
| `agent_num = 2` | 训练 2 个智能体，即 2 架无人机。 |
| `obs_dim = 15` | 每个智能体观测维度是 15。当前可理解为 5 个任务，每个任务 3 个字段。 |
| `action_dim = [5, 4]` | 动作是二维 MultiDiscrete：第 1 维选 5 个任务之一，第 2 维选 4 类传感器/动作之一。 |

训练入口中创建环境的位置：

```python
from envs.env_discrete import MultiDiscrete
env = MultiDiscrete([[0,4], [0,2]])
```

这里的 `[[0,4], [0,2]]` 表示 actor 输出两个离散动作维度：

```text
动作维度 1：任务编号，范围 0 到 4
动作维度 2：资源/传感器编号，范围 0 到 2
```

虽然 `EnvCore.action_dim = [5, 4]` 中第二维是 4，但环境初始化的可用动作掩码里第 2 维是：

```python
np.array([1, 1, 1, 0])
```

也就是第 4 个动作默认不可用。

## 4. 训练入口

进入训练目录：

```bash
cd F:/工作/173/代码/i-ssros/light_mappo-transformer/light_mappo-main
```

Linux 或 WSL 写法：

```bash
cd /path/to/i-ssros/light_mappo-transformer/light_mappo-main
```

启动训练：

```bash
python train/train.py
```

默认参数来自 `config.py` 和 `train/train.py`：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--algorithm_name` | `mappo` | 使用非循环 MAPPO。 |
| `--env_name` | `MyEnv` | 自定义环境名称。 |
| `--scenario_name` | `5tasks2UAVs` | 场景名。 |
| `--num_agents` | `2` | 智能体数量。 |
| `--n_rollout_threads` | `5` | 并行环境数量。 |
| `--episode_length` | `200` | 每个 episode 的步数。 |
| `--num_env_steps` | `10e4` | 总环境交互步数。 |
| `--share_policy` | `False` | 默认每个智能体单独一套 actor/critic。 |
| `--save_interval` | `1` | 每个 episode 都保存模型。 |
| `--log_interval` | `5` | 每 5 个 episode 打印/记录一次日志。 |

## 5. 从零训练前必须注意 model_dir

`config.py` 当前有一个重要默认值：

```python
parser.add_argument(
    "--model_dir",
    type=str,
    default = str(Path(__file__).resolve().parent / "results/MyEnv/5tasks2UAVs/mappo/check/run1/models"),
)
```

`runner/separated/base_runner.py` 中会判断：

```python
if self.model_dir is not None:
    self.restore()
```

这意味着：默认训练会先尝试从 `results/MyEnv/5tasks2UAVs/mappo/check/run1/models` 加载旧模型。

如果这个目录不存在，或者里面没有：

```text
actor_agent0.pt
critic_agent0.pt
actor_agent1.pt
critic_agent1.pt
```

训练会在初始化阶段失败。

因此从零训练时，应先把 `config.py` 中 `--model_dir` 的默认值改成：

```python
default=None
```

或者在代码里把判断改成：

```python
if self.model_dir:
    self.restore()
```

仅从命令行传 `--model_dir ""` 不够稳妥，因为当前代码判断的是 `is not None`，空字符串仍然会进入 `restore()`。

## 6. 推荐训练命令

依赖安装完成，并处理好 `model_dir` 后，可以先跑一个小规模 smoke test：

```bash
python train/train.py \
  --algorithm_name mappo \
  --env_name MyEnv \
  --scenario_name 5tasks2UAVs \
  --num_agents 2 \
  --n_training_threads 1 \
  --n_rollout_threads 5 \
  --episode_length 5 \
  --num_env_steps 25 \
  --experiment_name smoke_test \
  --save_interval 1 \
  --log_interval 1
```

这个命令只跑很少步数，用来确认：

1. 环境能 reset。
2. actor 能根据观测和动作掩码采样动作。
3. 环境能 step 并返回 reward/done/available_actions。
4. buffer 能插入数据。
5. PPO 能执行一次更新。
6. 模型能保存到 `results`。

确认 smoke test 正常后，再跑正式训练：

```bash
python train/train.py \
  --algorithm_name mappo \
  --env_name MyEnv \
  --scenario_name 5tasks2UAVs \
  --num_agents 2 \
  --n_training_threads 2 \
  --n_rollout_threads 5 \
  --episode_length 200 \
  --num_env_steps 100000 \
  --experiment_name check \
  --save_interval 1 \
  --log_interval 5
```

## 7. 训练过程代码链路

训练主流程在 `train/train.py`：

```text
get_config()
    -> parse_args()
    -> make_train_env()
    -> 初始化 Runner
    -> runner.run()
```

具体链路：

1. `train/train.py` 读取参数。
2. 根据 `cuda` 和本机 GPU 状态选择 `cuda:0` 或 `cpu`。
3. 创建结果目录：

```text
results/MyEnv/5tasks2UAVs/mappo/<experiment_name>/runN/
```

4. 调用 `make_train_env()` 创建 `DummyVecEnv`。
5. 因为 `share_policy=False`，加载：

```python
runner.separated.env_runner.EnvRunner
```

6. `base_runner.py` 为每个智能体创建：
   - `RMAPPOPolicy`
   - `RMAPPO`
   - `SeparatedReplayBuffer`
7. `EnvRunner.run()` 开始循环采样和训练。

## 8. 每个 episode 内部发生什么

`runner/separated/env_runner.py` 的 `run()` 是训练核心。

流程：

```text
warmup()
for episode in episodes:
    for step in episode_length:
        collect()
        envs.step()
        insert()
    compute()
    train()
    save()
    log_train()
```

每一步含义：

| 函数 | 作用 |
| --- | --- |
| `warmup()` | 调用环境 reset，拿到初始 obs 和 available_actions，写入 buffer 第 0 步。 |
| `collect(step)` | 对每个智能体调用 policy，根据 obs 和 available_actions 采样动作。 |
| `envs.step(actions_env)` | 将动作送入环境，得到下一步 obs、reward、done、info、available_actions。 |
| `insert(data)` | 将当前 transition 插入 replay buffer。 |
| `compute()` | 用 critic 估计最后状态价值，计算 return。 |
| `train()` | 对每个智能体执行 MAPPO/PPO 更新。 |
| `save()` | 保存 actor 和 critic 权重。 |
| `log_train()` | 写 TensorBoard 日志。 |

## 9. 环境 reward 和 done 逻辑

`envs/env_core.py` 中 `reset()` 会随机初始化 5 个任务：

```text
每个任务 3 个字段：
任务类型/状态、天气因素1、天气因素2
```

`step(actions)` 中，每个智能体动作会被解析为：

```python
Single_action = np.where(actions[i] == 1)
task = Single_action[0][0] * 3
sensor = Single_action[0][1] - self.action_dim[0]
```

含义：

| 动作部分 | 含义 |
| --- | --- |
| 第一个 one-hot 区间 | 选择任务。 |
| 第二个 one-hot 区间 | 选择传感器/资源。 |

reward 根据任务类型、传感器选择、天气因素计算：

```python
F1 = 0.6892 * exp(-14.2991 * weather1) + 0.1629
F2 = 2.1795 * exp(-2.2711 * weather2) - 1.1109
F = clip(F1 * F2, 0, 1)
```

当任务被完成时，任务状态会置为 `0`。如果所有任务状态都为 `0`，则：

```python
self.done = True
tmpreward += 1
```

同时环境会更新动作掩码：

```python
如果某个任务已完成，则该任务对应动作不可选
```

## 10. 动作掩码如何参与训练

环境 reset 时会返回：

```python
available_actions
```

结构大致是：

```text
[
  agent0: [任务动作掩码, 传感器动作掩码],
  agent1: [任务动作掩码, 传感器动作掩码]
]
```

在 `EnvRunner.collect()` 中：

```python
agent_masks = [env_actions[agent_id] for env_actions in self.available_actions]
```

每个智能体采样动作时会传入自己的动作掩码：

```python
policy.get_actions(..., tmp_masks)
```

此外，为避免多个智能体选择同一个任务，代码会把前面智能体已经选过的任务在后续智能体 mask 掉：

```python
for last_action in tmp_actions:
    for j in range(0,5):
        tmp_masks[j][0][last_action[j]] = 0
```

## 11. MAPPO 更新逻辑

`algorithms/algorithm/r_mappo.py` 实现 PPO 更新。

核心步骤：

1. 计算 advantage：

```python
advantages = returns - value_preds
```

2. 对 advantage 做标准化。
3. 根据是否使用 recurrent policy 选择数据生成器。
4. 调用 `ppo_update()`。
5. 计算 actor loss：

```text
min(ratio * advantage, clipped_ratio * advantage)
```

6. 加 entropy 正则。
7. 更新 actor。
8. 计算 critic value loss。
9. 更新 critic。

当前默认 `algorithm_name=mappo`，并且 `use_recurrent_policy=False`，所以默认走 feed-forward 训练，不走 RNN 轨迹训练。

## 12. 训练产物

训练输出目录格式：

```text
light_mappo-transformer/light_mappo-main/results/
  MyEnv/
    5tasks2UAVs/
      mappo/
        <experiment_name>/
          run1/
            models/
            logs/
```

模型保存文件：

```text
models/actor_agent0.pt
models/critic_agent0.pt
models/actor_agent1.pt
models/critic_agent1.pt
```

如果多次训练同一个 `experiment_name`，会自动生成：

```text
run1
run2
run3
...
```

## 13. 如何让训练结果用于 C++ 推理

C++ 选择插件最终调用：

```text
light_mappo-transformer/light_mappo-main/train/new.py
```

`new.py` 加载权重的位置是：

```python
project_root / "weights" / "5UAVs" / f"actor_agent{UAVid-1}.pt"
```

也就是说，推理默认不读取 `results/.../models`，而是读取：

```text
light_mappo-transformer/light_mappo-main/weights/5UAVs/
```

如果训练得到的新模型要给 C++ 使用，需要把训练产物中的 actor 权重复制到 `weights/5UAVs`：

```bash
cp results/MyEnv/5tasks2UAVs/mappo/check/run1/models/actor_agent0.pt weights/5UAVs/actor_agent0.pt
cp results/MyEnv/5tasks2UAVs/mappo/check/run1/models/actor_agent1.pt weights/5UAVs/actor_agent1.pt
```

当前训练环境是 2 个智能体，因此默认只会产生：

```text
actor_agent0.pt
actor_agent1.pt
```

但 `weights/5UAVs` 里有 5 个 actor 文件，C++ 推理按 `UAVid` 加载：

```text
UAVid=1 -> actor_agent0.pt
UAVid=2 -> actor_agent1.pt
UAVid=3 -> actor_agent2.pt
UAVid=4 -> actor_agent3.pt
UAVid=5 -> actor_agent4.pt
```

如果要支持 5 架无人机，应同步修改训练环境：

```python
EnvCore.agent_num = 5
```

并确认 `--num_agents 5`、动作掩码、runner 中相关硬编码也一致。

## 14. 当前代码中影响跑通的点

当前原始代码需要特别注意这些问题：

1. 缺依赖会直接导致训练启动失败：
   - `setproctitle`
   - `gym`
   - `tensorboardX`
   - `absl-py`
2. `config.py` 默认 `model_dir` 指向 `results/.../run1/models`，从零训练前应改成 `None`。
3. `runner/separated/env_runner.py` 中 `episode_rewards = np.zeros([5,self.num_agents,1])` 写死了 5 个 rollout 线程。因此默认 `--n_rollout_threads=5` 可以匹配；如果改成其他值，这里会 shape 不匹配。
4. 同一个文件最后保存 reward 曲线时：

```python
save_path = self.log_dir
plt.savefig(save_path)
```

`self.log_dir` 是目录，不是图片文件路径。训练结束保存曲线时可能失败。建议改成：

```python
save_path = os.path.join(self.log_dir, "reward_curve.png")
```

5. `envs/env_core.py` 中导入了 `pandas.conftest`、`sympy`、`tornado` 等非必要对象，增加了环境依赖。
6. `train/new.py` 的 `__main__` 测试调用少传了 `UAVid` 参数，直接运行 `python train/new.py` 会失败。C++ 插件调用时会传 `UAVid`，所以正式推理路径不受这个测试代码影响。

## 15. 建议的最小改动

为了让训练稳定从零跑通，建议至少做这几处修改：

1. `config.py`：

```python
default=None
```

2. `runner/separated/base_runner.py`：

```python
if self.model_dir:
    self.restore()
```

3. `runner/separated/env_runner.py`：

```python
episode_rewards = np.zeros([self.n_rollout_threads, self.num_agents, 1])
tmp = sum(episode_rewards) / self.n_rollout_threads
save_path = os.path.join(self.log_dir, "reward_curve.png")
```

4. 安装缺失依赖：

```bash
pip install gym tensorboardX setproctitle absl-py
```

完成这些后，再使用第 6 节的 smoke test 命令确认训练链路。

## 16. 训练到部署的完整步骤

完整流程如下：

1. 进入训练目录：

```bash
cd light_mappo-transformer/light_mappo-main
```

2. 安装依赖：

```bash
pip install gym tensorboardX setproctitle absl-py
```

3. 从零训练前处理 `model_dir` 默认值。
4. 先跑 smoke test：

```bash
python train/train.py --experiment_name smoke_test --episode_length 5 --num_env_steps 25 --n_rollout_threads 5 --log_interval 1
```

5. 跑正式训练：

```bash
python train/train.py --experiment_name check --episode_length 200 --num_env_steps 100000 --n_rollout_threads 5
```

6. 找到训练产物：

```text
results/MyEnv/5tasks2UAVs/mappo/check/runN/models/
```

7. 将需要部署的 actor 权重复制到：

```text
weights/5UAVs/
```

8. 启动 C++ IROS，选择插件会通过 `train/new.py` 加载这些 actor 权重进行动作选择。
