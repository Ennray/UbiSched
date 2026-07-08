# iS2ROS 冗余代码分析

本文档按“当前默认运行时是否会调用”来判断冗余代码。这里的当前默认运行时指：

```text
run_iros_yolo.sh
    -> ./IROS 8888 1
        -> iSSROS/main.cpp
        -> CapEngine::run()
        -> ContextRenewManager::serverGetEnvData()
        -> CapAdaptiveManager::run()
        -> 动态加载 libselect.so
        -> SelectPlugin::select()
        -> Python train/new.py::actor_inference()
        -> CapDispatchManager::run()
```

因此，本文中的“冗余”不是指文件一定没有价值，而是指在上述运行链路中没有被调用。训练、测试、历史备份、未来功能预留会单独标注。

## 1. 当前实际调用链路

当前 IROS 运行时会经过的核心代码如下：

| 模块 | 文件 |
| --- | --- |
| 程序入口 | `iSSROS/main.cpp` |
| 全局状态 | `iSSROS/Utils/Global.cpp` |
| 能力引擎 | `iSSROS/CapEngine.cpp` |
| UDP 状态接收 | `iSSROS/core/ContextRenewManager.cpp` 的 `serverGetEnvData()` |
| 能力需求构建 | `iSSROS/core/CapNeedManager.cpp` |
| 资源能力读取 | `iSSROS/CapInterface/CapInterfaceManager.cpp` |
| 自适应决策 | `iSSROS/core/CapAdaptiveManager.cpp` |
| 插件加载 | `iSSROS/plugin/PluginMgrImpl.cpp` |
| 选择插件 | `plugins/select/selectPlugin.cpp` |
| MAPPO 推理 | `light_mappo-transformer/light_mappo-main/train/new.py` |
| 模型结构 | `algorithms/algorithm/r_actor_critic.py` 及其依赖 |
| 推理环境空间 | `envs/env_discrete.py`、`envs/env_core.py`、`envs/env_wrappers.py` |
| 调度下发 | `iSSROS/core/CapDispatchManager.cpp` |

这些文件属于当前主链路，不应直接删除。

## 2. 编译了但当前运行时未调用的代码

### 2.1 评估插件 assess

相关文件：

```text
plugins/assess/
iSSROS/plugin/AssessAPI.h
iSSROS/assessment.py
iSSROS/bpnn.py
```

原因：

`CapAdaptiveManager.cpp` 中评估插件加载和调用逻辑被整段注释。当前实际执行的是选择插件 `libselect.so`，没有执行 `libAssessPlugin.so` 的加载和 `AssessPlugin::assess()`。

当前状态：

```text
Makefile 会编译 plugins/assess/build/libAssessPlugin.so
CapAdaptiveManager.cpp 里有 assessSearchPaths
但真正调用 assess 的代码在 /* ... */ 注释块里
```

结论：

在当前 IROS 运行链路中，`plugins/assess`、`iSSROS/assessment.py`、`iSSROS/bpnn.py` 都不参与运行。它们属于“评估功能预留/历史功能”，不是当前必需代码。

如果后续不再恢复能力评估阶段，可以考虑移除：

```text
plugins/assess/
iSSROS/plugin/AssessAPI.h
iSSROS/assessment.py
iSSROS/bpnn.py
Makefile 中 assess 编译步骤
CapAdaptiveManager.cpp 中 assessSearchPaths 和注释块
```

如果后续要恢复评估功能，则不建议删除。

### 2.2 位置接收线程 serverGetPosData

相关位置：

```text
iSSROS/main.cpp
iSSROS/core/ContextRenewManager.h
iSSROS/core/ContextRenewManager.cpp
```

原因：

`main.cpp` 中第三个线程被注释：

```cpp
// t[2] = thread(&ContextRenewManager::serverGetPosData,CRM);
```

`ContextRenewManager.cpp` 中 `serverGetPosData()` 的实现也整段被注释。

同时 `CapEngine.cpp` 里原本等待两个触发条件的逻辑也改成只等 `startAssess`：

```cpp
while(!(startAssess)){
```

不是：

```cpp
while(!(startAssess && startSelect)){
```

结论：

当前运行时不会接收位置数据，也不会使用 `startSelect` 触发选择。`serverGetPosData`、`startSelect` 相关逻辑属于旧功能或预留功能。

注意：

`main.cpp` 当前仍然有 `threadCount=3`，但只初始化了两个线程。这不是冗余代码，而是潜在运行问题，应改成 `threadCount=2` 或恢复第三个线程。

### 2.3 CapabilityCanUse 能力可用表

相关文件：

```text
iSSROS/Cap/CapabilityCanUse.h
iSSROS/Cap/CapabilityCanUse.cpp
plugins/select/Cap/CapabilityCanUse.h
```

原因：

当前选择逻辑已经改为直接构造：

```text
obs
rnn_states
available_actions
```

然后调用 MAPPO 推理。旧的 `CapabilityCanUse` 资源可用表没有进入当前选择插件调用链。

`Global.cpp` 中仍有：

```cpp
vector<CapabilityCanUse> resourceCapCanUseTB;
```

但当前主流程没有真正填充并使用它。

结论：

`CapabilityCanUse` 当前主要是旧版“能力评估 -> 可用能力 -> 选择匹配”流程遗留的数据结构。当前 MAPPO 选择链路不依赖它。

### 2.4 环境对象 Environment / Weather 在主流程中基本未使用

相关文件：

```text
iSSROS/env/Environment.*
iSSROS/env/Weather.*
iSSROS/env/Position.*
plugins/assess/env/*
```

原因：

`Environment` 和 `Weather` 原本服务于评估插件，用于根据光照、雾、雨、尘等环境因素评估传感器能力。但当前：

1. `ContextRenewManager::serverGetEnvData()` 不再构建 `curEnv`，相关代码被注释。
2. `AssessPlugin::assess()` 没有被当前主流程调用。
3. `CapAdaptiveManager.cpp` 的评估插件调用被注释。

结论：

当前 IROS 运行链路不依赖环境对象。保留它们只对恢复评估插件有意义。

## 3. 选择插件中的旧 MCTS 代码

相关文件：

```text
plugins/select/MTCTS.h
plugins/select/MTCTS.cpp
plugins/select/TNode.h
plugins/select/Uct.h
plugins/select/Uav.h
plugins/select/Sensor.h
plugins/select/TaskReq.h
plugins/select/Input.h
plugins/select/readme.md
```

原因：

当前 `plugins/select/selectPlugin.cpp` 中 `SelectPlugin::select()` 直接调用 Python：

```cpp
pModule = PyImport_ImportModule("new");
pFunc = PyObject_GetAttrString(pModule, "actor_inference");
```

旧 `plugins/select/readme.md` 里描述的是：

```cpp
MCTSTree::Select(resourceCapCanUseTB, capNeedTB)
```

但这已经不是当前 `SelectAPI` 的接口形态。当前 `SelectAPI` 接收的是：

```cpp
obs
rnn_states
available_actions
actions0
UAVid
```

另外，`plugins/select/CMakeLists.txt` 仍然把 `MTCTS.cpp` 编进 `libselect.so`：

```cmake
add_library(select SHARED
    selectPlugin.cpp
    PluginImpl.cpp
    MTCTS.cpp
)
```

但 `selectPlugin.cpp` 没有调用 `MCTSTree`。

结论：

MCTS 相关代码当前被编译进选择插件，但运行时没有被调用，属于旧版选择算法遗留。若只保留 MAPPO 选择，可以考虑从 CMake 中移除 `MTCTS.cpp`，并清理相关头文件和旧 readme。

## 4. MAPPO 训练/调试相关代码

这些代码不是 IROS 在线运行时调用的，但训练模型时可能需要，因此不能简单按“运行 IROS 不调用”就删除。

### 4.1 当前在线推理会调用的 MAPPO 文件

`train/new.py` 在线推理会用到：

```text
train/new.py
config.py
envs/env_discrete.py
envs/env_core.py
envs/env_wrappers.py
algorithms/algorithm/r_actor_critic.py
algorithms/utils/*
weights/5UAVs/actor_agent*.pt
```

这些属于在线推理链路，不是冗余。

### 4.2 只在训练时调用的文件

相关文件：

```text
train/train.py
runner/separated/*
utils/separated_buffer.py
utils/valuenorm.py
algorithms/algorithm/r_mappo.py
algorithms/algorithm/rMAPPOPolicy.py
```

原因：

IROS 在线运行时不会调用训练入口 `train/train.py`。但如果要重新训练 actor 权重，这些文件是必需的。

结论：

这些不是运行时必需代码，但属于训练功能代码，不建议删除。

### 4.3 当前默认训练不走的 shared runner

相关文件：

```text
runner/shared/base_runner.py
runner/shared/env_runner.py
utils/shared_buffer.py
```

原因：

`config.py` 中 `--share_policy` 使用：

```python
action="store_false", default=False
```

所以默认 `share_policy=False`，`train/train.py` 会进入：

```python
from runner.separated.env_runner import EnvRunner as Runner
```

不会进入：

```python
from runner.shared.env_runner import EnvRunner as Runner
```

结论：

shared runner 是“共享策略训练模式”的备用代码。默认训练不调用，但如果命令行启用共享策略，它可能会被调用。当前项目主配置不依赖它。

### 4.4 连续动作环境和普通离散动作环境

相关文件/类：

```text
envs/env_continuous.py
envs/env_discrete.py::DiscreteActionEnv
```

原因：

`train/train.py` 和 `train/new.py` 当前都明确使用：

```python
from envs.env_discrete import MultiDiscrete
env = MultiDiscrete(...)
```

`ContinuousActionEnv` 和 `DiscreteActionEnv` 只在注释里出现，没有被当前训练或推理实际调用。

结论：

它们是环境类型切换的示例/备用代码。若项目确定只使用 MultiDiscrete 动作空间，可视为可清理冗余。

### 4.5 旧 MPE 脚本和渲染脚本

相关文件：

```text
light_mappo-transformer/light_mappo-main/scripts/train_mpe.sh
light_mappo-transformer/light_mappo-main/scripts/render/render_mpe.py
```

原因：

`train_mpe.sh` 调用：

```bash
python train/train_mpe.py
```

但当前项目中没有 `train/train_mpe.py`。`render_mpe.py` 中导入路径也指向旧工程结构：

```python
from mappo.config import get_config
from mappo.envs.mpe.MPE_env import MPEEnv
from onpolicy.runner...
```

这些不匹配当前 `light_mappo-main` 目录结构。

结论：

这两个文件属于原 MAPPO/MPE 项目遗留脚本，当前项目运行和训练都不应依赖它们。

### 4.6 测试/加载脚本

相关文件：

```text
train/test.py
train/load_test.py
train/load_test'.py
```

原因：

这些文件没有被 IROS 主流程、`train/train.py` 或 `train/new.py` 导入。它们看起来是实验、加载测试或临时调试脚本。

结论：

当前运行时不调用。保留它们只对调试历史实验有意义。

## 5. 备份、测试和历史目录

相关路径：

```text
Baks/
iSSROS/test/
1.txt
```

原因：

这些文件不在 `run_iros_yolo.sh`、`Makefile` 当前主运行链路、IROS 主程序、选择插件、MAPPO 推理入口中。

结论：

它们属于备份/测试/记录类内容，当前运行时不调用。

## 6. 重复接口和拷贝文件

项目中存在主程序和插件各自复制一份接口/数据结构的情况：

```text
iSSROS/plugin/PluginImpl.h
plugins/select/PluginImpl.h
plugins/assess/PluginImpl.h

iSSROS/plugin/SelectAPI.h
plugins/select/SelectAPI.h

iSSROS/plugin/AssessAPI.h
plugins/assess/AssessAPI.h
```

原因：

插件是独立动态库，历史上可能为了独立编译复制了接口文件。但这会带来接口不一致风险。

当前状态：

`iSSROS/plugin/SelectAPI.h` 与 `plugins/select/SelectAPI.h` 都存在，主程序和插件分别编译自己的接口声明。只要签名一致可以运行；一旦一边改了另一边没改，动态转换或调用可能出问题。

结论：

这类代码不一定是运行冗余，但属于维护冗余。长期建议抽出公共 `include/` 目录，由主程序和插件共同引用同一份接口头文件。

## 7. 可优先清理清单

如果目标是减少当前 IROS 在线运行包体和维护负担，建议按风险从低到高处理。

### 低风险

这些基本不影响当前运行链路：

```text
light_mappo-transformer/light_mappo-main/scripts/train_mpe.sh
light_mappo-transformer/light_mappo-main/scripts/render/render_mpe.py
train/test.py
train/load_test.py
train/load_test'.py
iSSROS/test/
Baks/
```

### 中风险

这些是旧功能或备用模式，删除前确认不会恢复使用：

```text
plugins/select/MTCTS.*
plugins/select/TNode.h
plugins/select/Uct.h
plugins/select/Uav.h
plugins/select/Sensor.h
plugins/select/TaskReq.h
plugins/select/Input.h
plugins/select/readme.md
envs/env_continuous.py
envs/env_discrete.py::DiscreteActionEnv
runner/shared/
utils/shared_buffer.py
```

### 高风险

这些虽然当前不调用，但和历史评估功能关联较深。若后续还要恢复“评估 + 选择”两阶段流程，不应删除：

```text
plugins/assess/
iSSROS/plugin/AssessAPI.h
iSSROS/assessment.py
iSSROS/bpnn.py
iSSROS/env/Environment.*
iSSROS/env/Weather.*
CapabilityCanUse 相关代码
```

## 8. 建议

当前最合理的处理方式不是马上删除所有冗余，而是先确认项目未来只保留哪条主线：

1. 如果项目只保留“UDP 状态 -> MAPPO 选择 -> UDP 下发”，可以清理评估插件、MCTS 旧选择算法、MPE 脚本、测试脚本和备份目录。
2. 如果项目还要保留“能力评估 -> 可用能力 -> 选择匹配”的旧架构，则 `assess`、`Environment`、`CapabilityCanUse` 不应删除，只应标注为未启用模块。
3. 插件公共接口建议合并到一个公共头文件目录，避免主程序和插件各维护一份接口定义。
4. 清理前建议先修复 `main.cpp` 的 `threadCount=3` 问题，再跑一次当前 IROS 主链路，防止把运行问题和清理问题混在一起。
