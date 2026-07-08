# MAPPO 环境信息、传感器信息和动作信息流说明

本文说明当前 `i-ssros` 项目中，在“MAPPO 没有真正使用能力表”的前提下，环境信息、传感器可用信息和动作信息实际是如何生成、更新和传递的。

结论先说明：当前 MAPPO 的决策没有读取 `sensors.txt` 中的能力等级、功耗、状态、参数等字段，也没有通过 `CapabilityCanUse` 重新计算可用能力。MAPPO 实际依赖的是“观测向量 obs”和“可用动作掩码 available_actions”。训练阶段这些信息由 Python 环境 `EnvCore` 生成和更新；在线运行阶段这些信息由 C++ 的 `CapAdaptiveManager` 根据外部收到的 `obs0` 字符串临时构造。

## 1. 训练阶段的整体流程

训练入口在：

- `light_mappo-transformer/light_mappo-main/train/train.py`
- `light_mappo-transformer/light_mappo-main/envs/env_core.py`
- `light_mappo-transformer/light_mappo-main/envs/env_discrete.py`
- `light_mappo-transformer/light_mappo-main/runner/separated/env_runner.py`

训练时的数据流如下：

```text
train.py
  -> make_train_env()
  -> envs.env_discrete.MultiDiscrete
  -> EnvCore.reset()
  -> EnvRunner.warmup()
  -> EnvRunner.collect()
  -> policy.get_actions(obs, available_actions)
  -> 将 MAPPO 输出的 [任务编号, 传感器编号] 转成 one-hot
  -> EnvCore.step(actions)
  -> 更新 last_obs / reward / done / available_actions
  -> buffer.insert()
  -> train()
```

也就是说，MAPPO 训练时并不是直接改 C++ 里的环境或能力对象，而是通过 `EnvCore.step()` 改 Python 环境内部状态。

## 2. 训练阶段的环境信息如何生成

核心类是 `envs/env_core.py` 中的 `EnvCore`。

当前默认配置：

```python
self.agent_num = 2
self.obs_dim = 15
self.action_dim = [5, 4]
```

含义可以理解为：

- `agent_num = 2`：两个无人机智能体。
- `obs_dim = 15`：观测向量长度为 15。
- `action_dim = [5, 4]`：动作由两部分组成，第一维选择 5 个任务之一，第二维选择 4 类传感器/动作之一。

`last_obs` 是训练环境中的主要环境状态。长度为 15，可以按 5 个任务拆成 5 组，每组 3 个数：

```text
[任务0类型/状态, 任务0环境因子1, 任务0环境因子2,
 任务1类型/状态, 任务1环境因子1, 任务1环境因子2,
 ...
 任务4类型/状态, 任务4环境因子1, 任务4环境因子2]
```

在 `reset()` 中，`last_obs` 会随机初始化：

- 下标 `0, 3, 6, 9, 12` 是任务类型/任务状态，随机为 `1` 或 `2`。
- 其他下标是环境因子，使用 `np.random.beta(1.5, 4) * 10` 随机生成。

然后每个 agent 都拿到一份相同的 `last_obs` 拷贝作为自己的观测。

## 3. 训练阶段的传感器信息如何生成和更新

当前训练代码里，传感器可用性不是从能力表计算的，而是在 `EnvCore.reset()` 中硬编码初始化：

```python
self.available_actions.append([
    np.ones(self.action_dim[0]),
    np.array([1, 1, 1, 0])
])
```

这里 `available_actions` 对每个 agent 包含两组掩码：

```text
[
  [任务掩码: 5 个值],
  [传感器掩码: 4 个值]
]
```

默认含义：

- 任务掩码 `[1, 1, 1, 1, 1]`：5 个任务初始都可选。
- 传感器掩码 `[1, 1, 1, 0]`：前三类传感器/动作可选，第 4 类不可选。

也就是说，训练阶段的传感器可用性目前是固定的，不会根据 `sensors.txt`、能力等级、功耗或真实设备状态变化。

代码里有一个 `last_energy`，每个 agent 初始能量为 20：

```python
self.last_energy.append(20)
```

但是能量消耗和根据能量关闭传感器的逻辑都被注释掉了：

```python
# if self.last_energy[i] < 5:
#     self.available_actions[i][1][2] = 0
# if self.last_energy[i] < 2:
#     self.available_actions[i][1][1] = 0
# if self.last_energy[i] < 1:
#     self.available_actions[i][1][0] = 0
#     self.available_actions[i][1][3] = 1
```

因此当前训练里“传感器信息”的实际更新只有一个固定结论：传感器掩码基本保持 `[1, 1, 1, 0]`。

## 4. 训练阶段的动作信息如何产生

当前训练使用的是 `envs/env_discrete.py` 里的 `MultiDiscrete` 包装。

动作空间是：

```python
spaces.MultiDiscrete(self.signal_action_dim)
```

由于 `self.signal_action_dim = [5, 4]`，所以 MAPPO 输出的动作是两个离散编号：

```text
[task_idx, sensor_idx]
```

例如：

```text
[2, 1]
```

表示选择第 2 个任务，并使用第 1 类传感器/动作。

在 `runner/separated/env_runner.py` 的 `collect()` 中，MAPPO 会调用：

```python
policy.get_actions(..., tmp_masks)
```

这里的 `tmp_masks` 就是当前 agent 的可用动作掩码。模型输出 `[task_idx, sensor_idx]` 后，runner 会把它转换成 one-hot 拼接向量再交给环境：

```text
[任务 one-hot 5 维] + [传感器 one-hot 4 维]
```

例如动作 `[2, 1]` 会转成：

```text
[0, 0, 1, 0, 0, 0, 1, 0, 0]
```

前 5 位表示任务选择，后 4 位表示传感器/动作选择。

## 5. 训练阶段的环境如何被动作改变

动作真正改变环境的位置是 `EnvCore.step(actions)`。

环境会先从 one-hot 动作中解析出任务编号和传感器编号：

```python
Single_action = np.where(actions[i] == 1)
task = Single_action[0][0] * 3
sensor = Single_action[0][1] - self.action_dim[0]
```

这里 `task` 乘以 3，是因为 `last_obs` 中每个任务占 3 个位置。比如：

- 选择任务 0，对应 `last_obs[0]`
- 选择任务 1，对应 `last_obs[3]`
- 选择任务 2，对应 `last_obs[6]`

然后环境读取该任务的两个环境因子：

```python
weather1 = self.last_obs[task + 1]
weather2 = self.last_obs[task + 2]
```

并计算一个性能系数 `F`：

```python
F1 = 0.6892 * np.exp(-14.2991 * weather1) + 0.1629
F2 = 2.1795 * np.exp(-2.2711 * weather2) - 1.1109
F = np.clip(F1 * F2, 0, 1)
```

之后根据任务类型和传感器编号计算奖励，并可能把任务状态置为 0，表示任务完成。

当前规则大致是：

- 如果任务类型为 `1`：
  - 传感器 0：奖励受 `F` 影响，`F > 0.2` 时任务完成。
  - 传感器 1：任务直接完成。
  - 传感器 2：惩罚，不完成。
- 如果任务类型为 `2`：
  - 传感器 0：惩罚，不完成。
  - 传感器 1：惩罚，不完成。
  - 传感器 2：任务完成。

任务完成的实际表现是：

```python
self.last_obs[task] = 0
```

所以训练环境里，MAPPO 不是“改能力表”，而是通过动作让 `last_obs` 中对应任务位置从 `1/2` 变成 `0`。

## 6. 训练阶段环境因子如何更新

每次 `step()` 后，环境会重新随机刷新每个任务的两个环境因子：

```python
for i in range(0, 5):
    w1 = 3 * i + 1
    w2 = 3 * i + 2
    self.last_obs[w1] = random.randint(0, 1)
    self.last_obs[w2] = random.randint(0, 1)
```

这说明训练里的环境因子不是来自真实传感器或真实天气数据，而是每步随机生成的 0/1。

## 7. 训练阶段任务可用掩码如何更新

当某个任务完成后，`last_obs` 对应任务位置会变成 0。随后 `step()` 会更新任务掩码：

```python
for i in range(0, len(self.last_obs), 3):
    if self.last_obs[i] == 0:
        for j in range(0, self.agent_num):
            self.available_actions[j][0][i // 3] = 0
```

含义是：

- 如果任务已经完成，则所有 agent 都不能再选择该任务。
- 这个更新只影响任务掩码，不影响传感器掩码。

当所有任务状态都为 0 时，环境置为完成：

```python
if all(self.last_obs[i] == 0 for i in range(0, len(self.last_obs), 3)):
    self.done = True
    tmpreward += 1
```

## 8. Runner 里还有一层动作冲突处理

在 `EnvRunner.collect()` 中，除了环境返回的 `available_actions`，还额外做了一层临时掩码处理。

它会记录前面 agent 在同一个 step 里已经选择的任务：

```python
tmp_actions.append([a[0] for a in action])
```

然后对后面的 agent，把这些任务从 `tmp_masks` 中置为不可选：

```python
for last_action in tmp_actions:
    for j in range(0, 5):
        tmp_masks[j][0][last_action[j]] = 0
```

目的应该是避免多个 UAV 在同一步选择同一个任务。

不过这里有一个需要注意的问题：`tmp_masks = agent_masks.copy()` 是浅拷贝，内部数组仍然可能引用原来的 `available_actions`。因此这段“临时”屏蔽动作的代码，有可能意外修改原始掩码。这个问题不影响本文结论，但后续如果要严谨训练，建议改成深拷贝。

## 9. 在线运行阶段的信息从哪里来

在线运行阶段入口在：

- `iSSROS/core/CapAdaptiveManager.cpp`
- `light_mappo-transformer/light_mappo-main/train/new.py`
- `iSSROS/plugin/select/SelectPlugin.cpp` 或对应 select 插件代码

在线运行时不是调用 `EnvCore.step()`，也不会像训练环境那样随机更新 `last_obs`。它从外部通信收到一个全局字符串 `obs0`，然后在 `CapAdaptiveManager::run()` 中临时构造 MAPPO 输入。

### 9.1 观测 obs 的构造

代码把 `obs0` 每个字符转成数字：

```cpp
for (int i = 0; i < obs0.length(); i++) {
    obs[0].push_back(obs0[i] - '0');
}
```

所以在线推理时，MAPPO 的观测来自外部收到的 `obs0`，不是来自能力表。

### 9.2 任务掩码 tasks 的构造

任务掩码从 `obs0[1:]` 构造：

```cpp
for (int i = 1; i < obs0.length(); i++) {
    if (obs0[i] == '0') tasks.push_back(0);
    else tasks.push_back(1);
}
```

含义是：

- `obs0` 中某一位为 `0`，对应任务不可选。
- 非 `0`，对应任务可选。

注意：这里从 `i = 1` 开始，所以跳过了 `obs0` 的第 0 位。

### 9.3 传感器掩码 sensors 的构造

在线运行时传感器掩码也是硬编码：

```cpp
vector<float> sensors = {1, 1, 1, 0};
```

这和训练阶段初始化的传感器掩码一致。也就是说在线推理同样没有根据 `sensors.txt` 或能力表动态判断传感器是否可用。

### 9.4 调用 MAPPO 推理

最后 C++ 调用 select 插件：

```cpp
bool success = std::dynamic_pointer_cast<SelectAPI>(plug)->select(
    obs,
    rnn_states,
    available_actions,
    actions0,
    UAVid
);
```

select 插件再调用 Python 的 `train/new.py::actor_inference()`，加载对应 UAV 的 actor 权重，输出：

```text
[task_idx, sensor_idx]
```

## 10. 在线运行阶段动作如何落地

MAPPO 输出后，C++ 把动作写成一个任务到传感器的映射：

```cpp
map<int, int> res;
res[(int)actions0[0]] = (int)actions0[1];
resourceCapAllocatedTB = new CapabilityAllocated(res);
```

这里：

- `actions0[0]` 是任务编号。
- `actions0[1]` 是传感器/动作编号。

后续调度模块会把这个结果发送出去，形成类似：

```text
taskid#imageType#UAVid
```

因此在线阶段的动作信息实际是“MAPPO 根据 obs0 和硬编码掩码选择任务与传感器编号”，然后 C++ 把它转成 `CapabilityAllocated` 和调度消息。

## 11. 训练和在线运行的关键差异

当前代码里训练阶段和在线运行阶段并不是完全同一个环境闭环：

| 项目 | 训练阶段 | 在线运行阶段 |
| --- | --- | --- |
| 观测来源 | `EnvCore.reset()/step()` 内部随机生成和更新 `last_obs` | 外部通信收到的 `obs0` 字符串 |
| 任务状态更新 | `EnvCore.step()` 根据动作把任务状态置 0 | 不在 MAPPO 内部更新，由下一轮外部 `obs0` 决定 |
| 环境因子 | 每步随机刷新为 0/1 | 由 `obs0` 字符数字决定 |
| 任务掩码 | 根据 `last_obs` 中完成任务置 0 | 根据 `obs0[1:]` 是否为 0 构造 |
| 传感器掩码 | 固定 `[1,1,1,0]` | 固定 `[1,1,1,0]` |
| 能力表 | 未参与 | 未参与 |
| 能量机制 | 有变量但更新逻辑注释掉 | 未参与 |

## 12. 当前机制的实际含义

综合来看，当前 MAPPO 训练和推理中的“环境信息、传感器信息、动作信息”可以理解为：

1. 环境信息就是 `obs`/`last_obs`。
   - 训练时由 Python 随机环境维护。
   - 在线时由外部 `obs0` 输入。

2. 传感器信息就是 `available_actions` 的第二组掩码。
   - 当前固定为 `[1,1,1,0]`。
   - 没有根据真实能力、传感器状态、能量或功耗动态变化。

3. 动作信息就是 MAPPO 输出的 `[任务编号, 传感器编号]`。
   - 训练时会被转成 one-hot，传给 `EnvCore.step()` 更新 `last_obs` 和奖励。
   - 在线时会被 C++ 写入 `CapabilityAllocated`，再交给调度流程发送。

4. 当前所谓“环境变化”主要发生在训练环境内部。
   - 任务完成：`last_obs[task] = 0`
   - 环境因子刷新：每步随机变成 0 或 1
   - 任务掩码关闭：完成任务对应 mask 置 0

5. 当前所谓“传感器变化”基本没有真正发生。
   - 传感器掩码固定。
   - 能量消耗和低能量禁用传感器逻辑被注释。
   - 能力系统的数据没有接入 MAPPO 掩码。

## 13. 如果后续要让 MAPPO 真正用上能力

如果后续要让能力表真正影响 MAPPO，建议从这三个位置改：

1. 训练环境 `EnvCore.reset()/step()`
   - 把 `available_actions[j][1]` 从固定 `[1,1,1,0]` 改成由能力状态、能量或传感器状态动态计算。

2. 在线运行 `CapAdaptiveManager.cpp`
   - 把 `vector<float> sensors = {1,1,1,0}` 改成根据 `resourceCapTB`、`CapabilityCanUse` 或实际传感器状态生成。

3. 观测向量 `obs`
   - 如果希望 MAPPO 学会能力差异，训练和在线都需要把能力相关特征放进 obs，且保持维度和含义一致。

否则即使 C++ 侧读取了 `sensors.txt`，MAPPO 也仍然只能看到固定传感器掩码，学不到真实能力差异。
