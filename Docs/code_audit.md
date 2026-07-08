# iS2ROS + MAPPO 感知资源调度代码审计

## 1. 项目运行流程

### 1.1 程序入口

当前在线运行入口是 `iSSROS/main.cpp`。

程序启动参数：

```text
./iSSROS <listening_port> <UAVid>
```

其中：

- `listening_port` 写入全局变量，用于 UDP 接收仿真状态。
- `UAVid` 写入全局变量，用于选择对应 MAPPO actor 权重，并决定调度结果发送端口。

`main()` 主要启动两个线程：

```text
ContextRenewManager::serverGetEnvData()
CapEngine::run()
```

第三个位置数据接收线程 `serverGetPosData()` 已被注释，没有参与当前运行流程。

### 1.2 状态数据输入

状态输入在 `iSSROS/core/ContextRenewManager.cpp::serverGetEnvData()` 中完成。

该函数创建 UDP socket，绑定 `listening_port`，循环接收外部仿真消息。当前支持两类输入格式：

```text
time#light#fog#rain#dust#obs0
```

或无法解析为环境字段时，直接把整段 UDP payload 当作 `obs0`。

当消息字段数不少于 5 时，代码会构建：

- `Weather`：使用 `fog`、`rain`、`dust`
- `Environment`：使用 `time`、`light`、`Weather`
- 全局 `curEnv`
- 全局 `obs0`，如果存在第 6 个字段

接收成功后设置：

```cpp
startAssess = true;
```

该标志会触发能力评估、选择和调度流程。

### 1.3 任务需求构建

任务需求由 `iSSROS/core/CapNeedManager.cpp::buildCapNeedTB()` 构建。

当前代码没有从需求文件读取任务，也没有解析结构化任务对象，而是直接读取全局字符串 `obs0`：

```cpp
for (int i = weathernums; i < obs0.length(); i++) {
    CapNeedTB->add(obs0[i] - '0', 10, 0.8);
}
```

其中全局 `weathernums = 1`，所以默认跳过 `obs0[0]`，从 `obs0[1]` 开始逐字符生成 `CapabilityNeed`。

每个需求项包含：

- `capneedid = obs0[i] - '0'`
- `lasttime = 10`
- `leveldemand = 0.8`

因此，当前任务需求本质上是 `obs0` 字符串的字符级转换，而不是基于真实任务模型或资源能力模型构造。

### 1.4 感知资源读取

感知资源读取在 `iSSROS/CapInterface/CapInterfaceManager.cpp::getCapabilityFromTxt()` 中完成。

`CapEngine::run()` 初始化时调用：

```cpp
resourceCapTB = CIM->getCapabilityFromTxt("./sensors.txt");
```

当前资源文件为 `iSSROS/sensors.txt`，格式为：

```text
id|name|status|type|vehicleName|power|resolution|fov|level|position
```

解析后生成 `Capability` 对象，主要字段包括：

- `id`
- `name`
- `status`
- `vehicleName`
- `power`
- `Parameter`：`resolution`、`fov`
- `level`
- `Position`

注意：虽然这些属性会进入 `resourceCapTB`，但当前 MAPPO 选择流程没有把 `resourceCapTB` 作为推理输入。

### 1.5 能力评估插件调用

能力评估在 `iSSROS/core/CapAdaptiveManager.cpp::run()` 中触发。

流程如下：

```text
CapAdaptiveManager::run()
  -> PluginMgr::LoadLibrary(libAssessPlugin.so)
  -> InitPlugin()
  -> AssessAPI::assess(resourceCapTB, curEnv)
  -> plugins/assess/AssessPlugin.cpp
  -> Python assessment.py::eoAssess / irAssess
```

`AssessPlugin::assess()` 会根据资源名称选择评估函数：

- `EOCap` / `RGBCap*` -> `eoAssess`
- `IRCap*` -> `irAssess`

评估输入来自 `curEnv`：

- `light`
- `fog`
- `rain`
- `dust`

评估结果会追加到对应 `Capability.level` 中。

关键问题是：评估后的 `Capability.level` 没有进入 MAPPO 的 `obs` 或 `available_actions`，所以评估结果目前只改变 C++ 能力表对象，不影响最终 MAPPO 决策。

### 1.6 选择插件和 Python MAPPO 调用

选择流程同样在 `CapAdaptiveManager::run()` 中。

调用链：

```text
CapAdaptiveManager::run()
  -> PluginMgr::LoadLibrary(libselect.so)
  -> InitPlugin()
  -> SelectAPI::select(obs, rnn_states, available_actions, actions0, UAVid)
  -> plugins/select/selectPlugin.cpp::SelectPlugin::select()
  -> Python train/new.py::actor_inference()
  -> R_Actor
  -> weights/5UAVs/actor_agent{UAVid-1}.pt
```

C++ 端构造 MAPPO 输入的方式如下。

`obs`：

```cpp
for (int i = 0; i < obs0.length(); i++) {
    obs[0].push_back(obs0[i] - '0');
}
```

即把 `obs0` 每个字符转成一个数字。

`rnn_states`：

```cpp
vector<float> rnn_states(64, 0.0);
```

每次推理都是全 0。

`available_actions`：

```cpp
for (int i = 1; i < obs0.length(); i++) {
    if (obs0[i] == '0') tasks.push_back(0);
    else tasks.push_back(1);
}

vector<float> sensors = {1, 1, 1, 0};
available_actions[0].push_back(tasks);
available_actions[0].push_back(sensors);
```

含义：

- 任务动作掩码来自 `obs0[1:]`，非 0 代表可选，0 代表不可选。
- 传感器动作掩码固定为 `[1, 1, 1, 0]`。

Python 推理在 `light_mappo-transformer/light_mappo-main/train/new.py::actor_inference()` 中执行：

1. 加载配置。
2. 创建 `MultiDiscrete([[0, 4], [0, 2]])` 环境包装，仅用于获得 observation/action space。
3. 创建 `R_Actor`。
4. 根据 `UAVid` 加载：

```text
weights/5UAVs/actor_agent{UAVid-1}.pt
```

5. 调用 actor：

```python
actions0, _, _ = actor0(
    obs,
    np.zeros(64),
    np.ones(10),
    available_actions
)
```

返回值是：

```text
[task_idx, sensor_idx]
```

### 1.7 调度结果输出

MAPPO 返回动作后，`CapAdaptiveManager::run()` 将其转换为 `CapabilityAllocated`：

```cpp
map<int, int> res;
res[(int)actions0[0]] = (int)actions0[1];
resourceCapAllocatedTB = new CapabilityAllocated(res);
```

随后 `CapEngine::run()` 调用：

```cpp
CapDispatchManager::run(resourceCapAllocatedTB);
```

`CapDispatchManager::run()` 将结果封装为 UDP 消息：

```text
taskid#imageType#UAV{UAVid}
```

发送目标：

- IP：从 `config.ini` 的 `DEST_IP_ADDRESS` 读取，失败时回退到 `192.168.137.1`
- 端口：`9999 - UAVid + 1`

例如 `UAVid = 1` 时发送到 `9999`，`UAVid = 2` 时发送到 `9998`。

## 2. 核心文件和核心函数

| 文件名 | 函数名 | 作用 | 输入 | 输出 |
| --- | --- | --- | --- | --- |
| `iSSROS/main.cpp` | `main` | 程序入口，读取监听端口和 UAV 编号，启动状态接收线程和能力引擎线程 | `argv[1]=port`，`argv[2]=UAVid` | 后台线程持续运行 |
| `iSSROS/core/ContextRenewManager.cpp` | `serverGetEnvData` | UDP 接收仿真环境和观测状态，更新 `curEnv`、`obs0`、`startAssess` | UDP payload | 全局 `curEnv`、`obs0`、`startAssess=true` |
| `iSSROS/CapEngine.cpp` | `CapEngine::run` | 总调度循环，构建需求、读取资源、等待状态、调用自适应选择和结果派发 | 全局状态、`sensors.txt` | 调用评估/选择/派发流程 |
| `iSSROS/core/CapNeedManager.cpp` | `buildCapNeedTB` | 从 `obs0` 构造能力需求表 | 全局 `obs0`、`weathernums` | 全局 `capNeedTB` |
| `iSSROS/CapInterface/CapInterfaceManager.cpp` | `getCapabilityFromTxt` | 从 `sensors.txt` 读取感知资源能力 | 资源文件路径 | `vector<Capability*>` |
| `iSSROS/core/CapAdaptiveManager.cpp` | `CapAdaptiveManager::run` | 加载评估插件和选择插件，构造 MAPPO 输入，写入调度分配结果 | `resourceCapTB`、`curEnv`、`obs0`、`UAVid` | 全局 `resourceCapAllocatedTB` |
| `plugins/assess/AssessPlugin.cpp` | `AssessPlugin::assess` | 根据环境状态调用 Python 能力评估函数，追加能力等级 | `vector<Capability*>`、`Environment*` | 修改 `Capability.level` |
| `iSSROS/assessment.py` | `eoAssess` / `irAssess` | 计算 EO/IR 能力评估结果 | `light`、`fog`、`rain`、`dust` | `[detection, recognition, ranging]` |
| `plugins/select/selectPlugin.cpp` | `SelectPlugin::select` | C++/Python 桥接，导入 `new.py` 并调用 MAPPO actor 推理 | `obs`、`rnn_states`、`available_actions`、`UAVid` | `actions0=[task_idx, sensor_idx]` |
| `light_mappo-transformer/light_mappo-main/train/new.py` | `actor_inference` | 加载指定 UAV 的 actor 权重并执行在线推理 | `obs`、`rnn_states`、`available_actions`、`UAVid` | 动作列表 `[task_idx, sensor_idx]` |
| `light_mappo-transformer/light_mappo-main/envs/env_core.py` | `EnvCore.reset` | 训练环境初始化观测、能量和动作掩码 | 无 | `sub_agent_obs`、`available_actions` |
| `light_mappo-transformer/light_mappo-main/envs/env_core.py` | `EnvCore.step` | 训练阶段根据动作更新任务状态、奖励和动作掩码 | one-hot 动作 | 新观测、奖励、done、info、动作掩码 |
| `iSSROS/core/CapDispatchManager.cpp` | `CapDispatchManager::run` | 将 MAPPO 选择结果转成 UDP 调度命令并发送 | `CapabilityAllocated*` | UDP 消息 |
| `iSSROS/Cap/Capability.cpp` | `Capability` getter/setter/build/show | 表示单个感知能力资源 | 资源字段 | `Capability` 对象 |
| `iSSROS/Cap/CapabilityNeed.cpp` | `CapabilityNeed::add` | 添加单个能力需求项 | 能力 id、持续时间、等级需求 | 更新需求表 |
| `iSSROS/Cap/CapabilityAllocated.cpp` | `CapabilityAllocated` 构造与访问函数 | 保存任务到资源/传感器动作的分配结果 | `map<int,int>` | 分配表 |

## 3. 模块属性判断

### 3.1 与感知资源管理直接相关的模块

这些模块直接表示、读取、评估或分配感知资源：

- `iSSROS/Cap/Capability.*`
- `iSSROS/Cap/CapabilityNeed.*`
- `iSSROS/Cap/CapabilityCanUse.*`
- `iSSROS/Cap/CapabilityAllocated.*`
- `iSSROS/Cap/Parameter.*`
- `iSSROS/Resource/Resource.*`
- `iSSROS/CapInterface/CapInterfaceManager.*`
- `iSSROS/core/CapNeedManager.*`
- `iSSROS/core/CapAdaptiveManager.*`
- `iSSROS/core/CapDispatchManager.*`
- `plugins/assess/*`
- `plugins/select/*`
- `iSSROS/sensors.txt`
- `iSSROS/assessment.py`
- `light_mappo-transformer/light_mappo-main/train/new.py`
- `light_mappo-transformer/light_mappo-main/envs/env_core.py`
- `light_mappo-transformer/light_mappo-main/envs/env_discrete.py`

说明：

- `Capability`、`CapabilityNeed`、`CapabilityAllocated` 是资源管理的核心数据结构。
- `CapInterfaceManager` 负责资源能力表输入。
- `AssessPlugin` 负责环境相关能力评估。
- `SelectPlugin` 和 `new.py` 负责资源选择决策。
- `CapDispatchManager` 负责把选择结果落地为仿真执行命令。

### 3.2 平台支撑或通信支撑模块

这些模块主要负责程序运行、插件加载、全局变量、配置读取、网络通信等，不直接表达资源决策逻辑：

- `iSSROS/main.cpp`
- `iSSROS/Utils/Utils.*`
- `iSSROS/Utils/Global.cpp`
- `iSSROS/Utils/Single_T.*`
- `iSSROS/plugin/PluginMgr.*`
- `iSSROS/plugin/PluginMgrImpl.*`
- `iSSROS/plugin/PluginImpl.*`
- `iSSROS/core/ContextRenewManager.*`
- `iSSROS/env/Environment.*`
- `iSSROS/env/Weather.*`
- `iSSROS/env/Position.*`
- `config.ini`
- `Makefile`、`CMakeLists.txt`、构建脚本

说明：

- `ContextRenewManager` 虽然接收环境和 `obs0`，但职责是通信和上下文刷新，本身不做资源选择。
- `Environment`、`Weather`、`Position` 是环境数据载体，只有在评估插件中用于能力评估。
- 插件管理器只负责动态库加载，不关心选择算法语义。

## 4. 当前 MAPPO 决策实际使用的状态信息

### 4.1 在线推理实际使用的信息

当前在线 MAPPO 决策真正进入 actor 的信息只有以下几类。

#### 1. `obs0` 字符串转成的观测向量

位置：

```text
iSSROS/core/CapAdaptiveManager.cpp
```

构造方式：

```cpp
obs[0].push_back(obs0[i] - '0');
```

含义：

- `obs0` 的每个字符都被当作一个独立数值特征。
- 当前代码没有校验 `obs0` 是否为训练时的 15 维结构。
- 当前代码没有解析浮点数、多位数或分隔符，只支持字符级数字。

#### 2. 任务动作掩码

位置：

```text
iSSROS/core/CapAdaptiveManager.cpp
```

构造方式：

```cpp
for (int i = 1; i < obs0.length(); i++) {
    if (obs0[i] == '0') tasks.push_back(0);
    else tasks.push_back(1);
}
```

含义：

- `obs0[1:]` 中非 0 的位置对应可选任务。
- `obs0[1:]` 中为 0 的位置对应不可选任务。
- 这不是从 `CapabilityNeed` 或任务对象推导出来的，而是再次直接从 `obs0` 推导。

#### 3. 固定传感器动作掩码

位置：

```text
iSSROS/core/CapAdaptiveManager.cpp
```

构造方式：

```cpp
vector<float> sensors = {1, 1, 1, 0};
```

含义：

- 前 3 类传感器/动作永远可选。
- 第 4 类传感器/动作永远不可选。
- 不随 `sensors.txt`、资源在线状态、能力等级、功耗、位置或环境评估结果变化。

#### 4. `UAVid`

位置：

```text
plugins/select/selectPlugin.cpp
light_mappo-transformer/light_mappo-main/train/new.py
```

用途：

- 选择加载哪个 actor 权重：

```text
weights/5UAVs/actor_agent{UAVid-1}.pt
```

`UAVid` 不作为 actor 的观测特征输入，只影响模型文件选择。

#### 5. 全 0 RNN 状态和固定 mask

`rnn_states` 在 C++ 中固定为 64 维全 0。

Python 调用 actor 时第三个参数固定为：

```python
np.ones(10)
```

因此在线推理没有跨时刻记忆状态，也没有维护上一时刻 recurrent hidden state。

### 4.2 训练环境使用的信息

训练环境在 `EnvCore` 中定义：

```python
self.agent_num = 2
self.obs_dim = 15
self.action_dim = [5, 4]
```

训练时的观测可理解为 5 个任务，每个任务 3 个字段：

```text
[task_state/type, weather_factor_1, weather_factor_2] * 5
```

训练时的传感器掩码同样固定初始化为：

```python
np.array([1, 1, 1, 0])
```

训练环境中存在 `last_energy`，但能量消耗和基于能量关闭传感器的逻辑已经注释，没有实际进入动作掩码。

## 5. 存在但未真正进入 MAPPO 决策的资源属性

下列属性在代码或配置中存在，但当前没有进入在线 MAPPO actor 的 `obs` 或有效 `available_actions`。

| 属性/数据 | 出现位置 | 当前用途 | 是否进入 MAPPO 决策 | 说明 |
| --- | --- | --- | --- | --- |
| 资源 `id` | `sensors.txt`、`Capability.id` | 构建能力对象、打印 | 否 | 没有映射到动作编号或观测特征 |
| 资源 `name` | `sensors.txt`、`Capability.name` | 评估插件选择 EO/IR 函数 | 间接且不闭环 | 只影响评估函数，评估结果未进入 MAPPO |
| 资源 `status` | `sensors.txt`、`Capability.status` | 评估插件跳过离线资源 | 否 | 不影响在线传感器 mask，离线资源仍不会让 `[1,1,1,0]` 改变 |
| 资源 `type` | `sensors.txt` | 解析字段 | 否 | 当前 `CapabilityBuilder` 未设置 type，决策也不用 |
| `vehicleName` | `sensors.txt`、`Capability.vehicleName` | 打印、评估日志、dispatch 构造 UAV 名 | 否 | dispatch 使用的是全局 `UAVid`，不是资源表中的 vehicleName |
| `power` | `sensors.txt`、`Capability.power` | 解析和打印 | 否 | 未进入 obs、reward、mask 或 dispatch 选择 |
| `resolution` | `sensors.txt`、`Parameter` | 解析和打印 | 否 | 未进入能力筛选或 MAPPO 输入 |
| `fov` | `sensors.txt`、`Parameter` | 解析和打印 | 否 | 未进入能力筛选或 MAPPO 输入 |
| 初始 `level` | `sensors.txt`、`Capability.level` | 解析和打印 | 否 | 没有进入 `available_actions` 或 `obs` |
| 评估追加 `level` | `AssessPlugin::assess` | 追加到 `Capability.level` | 否 | 评估完成后没有被选择插件读取 |
| `Position` | `sensors.txt`、`Capability.position` | 解析保存；位置接收线程已注释 | 否 | 不参与距离、覆盖或动作 mask |
| `CapabilityNeed` | `CapNeedManager` | 从 `obs0` 生成需求表并打印 | 否 | 选择阶段没有读取 `capNeedTB` 内容 |
| `CapabilityCanUse` | `CapabilityCanUse.*`、全局 `resourceCapCanUseTB` | 数据结构存在 | 否 | 当前选择流程没有构造或使用可用能力表 |
| `curEnv.time` | `Environment` | 接收保存 | 否 | 评估插件不用 time，MAPPO 也不用 |
| `curEnv.light/fog/rain/dust` | `ContextRenewManager`、`AssessPlugin` | 能力评估输入 | 否 | 只影响评估结果，评估结果未进入 MAPPO |
| `last_energy` | `EnvCore` | 训练环境变量 | 否 | 能量更新和能量 mask 逻辑被注释 |

## 6. 审计结论

当前系统的运行链路已经具备完整框架：

```text
UDP 状态输入
  -> 构建 Environment / obs0
  -> 构建 CapabilityNeed
  -> 读取 sensors.txt
  -> 评估插件更新 Capability.level
  -> 选择插件调用 Python MAPPO
  -> 生成 CapabilityAllocated
  -> UDP 输出调度结果
```

但从决策闭环看，当前 MAPPO 在线选择实际只依赖：

```text
obs0 字符级观测
obs0[1:] 生成的任务可选 mask
固定传感器 mask [1,1,1,0]
UAVid 对应的 actor 权重
```

感知资源管理相关对象虽然存在，包括 `Capability`、`CapabilityNeed`、`CapabilityCanUse`、`CapabilityAllocated`、`sensors.txt` 和评估插件，但除了最终 `CapabilityAllocated` 用于 dispatch 外，大部分资源属性没有真正进入 MAPPO 决策。

对你的研究方向“基于多智能体强化学习的异构 UAV 集群感知资源与计算任务协同实时调度”而言，当前代码更接近：

```text
基于外部 obs0 的 MAPPO 任务-传感器编号选择系统
```

而还不是严格意义上的：

```text
基于异构 UAV 资源状态、感知能力、计算能力、任务需求和环境变化的协同实时调度系统
```

后续如果要支撑论文方向，关键改造点是把异构资源属性和任务计算需求接入 MAPPO 的训练环境与在线推理输入，并保证训练阶段和在线阶段的 `obs`、`available_actions` 语义一致。

