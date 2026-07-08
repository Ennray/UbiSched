# iS2ROS 能力代码实际使用情况分析

本文档专门回答一个问题：当前 `i-ssros` 运行时，是否真的使用了“能力”代码参与决策？

结论先说清楚：

```text
当前代码中有能力相关的数据结构，也会读取 sensors.txt 并构建 Capability 对象；
但这些能力对象没有真正参与 MAPPO 决策，也没有影响最终下发结果。
```

换句话说，当前“能力”更多停留在“读取、构建、打印、历史接口保留”的层面。真正影响选择结果的是 `obs0` 字符串和固定写死的动作掩码。

## 1. 当前运行链路

当前默认运行链路如下：

```text
UDP 收到状态字符串
    -> ContextRenewManager 写入 obs0
    -> CapNeedManager 根据 obs0 构建 capNeedTB
    -> CapEngine 读取 sensors.txt 到 resourceCapTB
    -> CapAdaptiveManager 根据 obs0 构造 obs 和 available_actions
    -> SelectPlugin 调用 Python actor_inference
    -> 返回 actions0
    -> CapabilityAllocated 封装 actions0
    -> CapDispatchManager 下发 taskid#imageType#UAVid
```

关键点是：

```text
resourceCapTB 没有传入 SelectPlugin
Capability 的 level/power/status/parameter/position 没有进入 actor_inference
capNeedTB 只检查是否构建，没有用于构造最终选择输入
```

## 2. 能力相关代码有哪些

当前项目中能力相关代码主要包括：

| 文件 | 作用 |
| --- | --- |
| `iSSROS/Cap/Capability.*` | 描述资源能力，如名称、状态、等级、参数、位置、功耗。 |
| `iSSROS/Cap/CapabilityNeed.*` | 描述任务能力需求。 |
| `iSSROS/Cap/CapabilityCanUse.*` | 历史上用于表示评估后可用能力。当前主流程未使用。 |
| `iSSROS/Cap/CapabilityAllocated.*` | 表示最终分配结果，当前仍在使用。 |
| `iSSROS/CapInterface/CapInterfaceManager.*` | 从 `sensors.txt` 读取能力资源。 |
| `iSSROS/sensors.txt` | 资源能力配置文件。 |
| `plugins/assess/*` | 评估插件，设计上用于评估能力，但当前未启用。 |
| `plugins/select/MTCTS.*` | 旧选择算法，设计上使用 `CapabilityCanUse` 和 `CapabilityNeed`，当前未调用。 |

## 3. sensors.txt 是否被读取

是，被读取了。

在 `CapEngine.cpp` 中：

```cpp
resourceCapTB = CIM->getCapabilityFromTxt("./sensors.txt");
resourceCapTBReady = true;
cout << "感知资源属性：" << endl;
for (int i = 0; i < resourceCapTB.size(); ++i) {
    resourceCapTB[i]->show();
}
```

`CapInterfaceManager::getCapabilityFromTxt()` 会解析 `sensors.txt`：

```text
id|name|status|type|vehicleName|power|resolution|fov|level|position
```

例如：

```text
1|EOCap|1|0|UAV1|2.5|1920x1080|87.3|70,50,60|10.0,20.0,30.0
```

这些字段会构建成 `Capability`：

```cpp
Capability* cap = capBuilder
    ->id(id)
    ->name(name)
    ->status(status)
    ->vehicle(vehicleName)
    ->power(power)
    ->level(level)
    ->parameter(*param)
    ->build();
cap->setPosition(pos);
```

所以，能力配置确实被读取成对象。

但后续没有把这些对象用于选择。

## 4. 能力需求 capNeedTB 是否被构建

是，被构建了。

`CapNeedManager.cpp` 中：

```cpp
CapNeedTB = new CapabilityNeed();
for(int i=weathernums;i<obs0.length();i++){
    CapNeedTB->add(obs0[i]-'0',10,0.8);
}
capNeedTB = CapNeedTB;
build = true;
```

也就是说，`capNeedTB` 来自 `obs0`，跳过前 `weathernums` 位后，每个字符构造一条需求。

但这里有两个问题：

1. `CapabilityNeed::add()` 的第三个参数是 `int demand`，调用传入 `0.8` 会被截断成 `0`。
2. 当前 `CapAdaptiveManager` 只检查 `CNM->isBuild()`，没有读取 `capNeedTB` 的具体内容参与选择。

`CapAdaptiveManager.cpp` 中只做了：

```cpp
auto CNM = CapNeedManager::GetInst();
if (!CNM->isBuild()) {
    cerr << "capNeedTB未构建！" << endl;
    return;
}
```

后续没有使用：

```cpp
capNeedTB->getcapneed(...)
```

也没有把 `capNeedTB` 传给选择插件。

因此能力需求表只是被构建和检查，并没有真正参与决策。

## 5. 选择插件是否使用 Capability

当前不使用。

当前 `SelectAPI` 接口是：

```cpp
virtual bool select(
    const vector<vector<float>>& obs,
    const vector<float>& rnn_states,
    const vector<vector<vector<float>>>& available_actions,
    vector<float>& actions0,
    int UAVid
) = 0;
```

这里没有传入：

```text
resourceCapTB
capNeedTB
resourceCapCanUseTB
Capability
CapabilityNeed
CapabilityCanUse
```

`SelectPlugin::select()` 只是把这几个参数转换成 Python list，然后调用：

```python
actor_inference(obs, rnn_states, available_actions, UAVid)
```

因此选择插件当前没有机会读取能力表。

## 6. CapAdaptiveManager 实际传给 MAPPO 的是什么

`CapAdaptiveManager.cpp` 中真正构造 MAPPO 输入的是这段：

```cpp
vector<vector<float>> obs;
obs.push_back(vector<float>());
for (int i = 0; i < obs0.length(); i++) {
    obs[0].push_back(obs0[i] - '0');
}
```

也就是直接把 `obs0` 每个字符转成数字，作为模型观测。

动作掩码构造如下：

```cpp
vector<float> tasks;
for (int i = 1; i < obs0.length(); i++) {
    if (obs0[i] == '0') tasks.push_back(0);
    else tasks.push_back(1);
}

vector<float> sensors = {1, 1, 1, 0};
available_actions.push_back(a);
available_actions[0].push_back(tasks);
available_actions[0].push_back(sensors);
```

这说明：

| 输入 | 来源 | 是否来自能力表 |
| --- | --- | --- |
| `obs` | `obs0` 字符串 | 否 |
| `tasks` mask | `obs0[1:]` 是否为 0 | 否 |
| `sensors` mask | 固定 `{1,1,1,0}` | 否 |
| `UAVid` | 命令行参数 | 否 |

其中 `sensors` 是写死的，和 `sensors.txt` 中的 `EOCap`、`IRCap`、`status`、`power`、`level` 没有关系。

## 7. 最终下发结果是否使用 Capability

当前不使用。

`CapAdaptiveManager` 得到 `actions0` 后：

```cpp
map<int, int> res;
res[(int)actions0[0]] = (int)actions0[1];
resourceCapAllocatedTB = new CapabilityAllocated(res);
```

`CapDispatchManager.cpp` 中：

```cpp
tmp->setImageType(iter->second);
tmp->setVehicleName("UAV"+to_string(UAVid));
tmp->setTaskid(iter->first);
tmp->setResourceName(std::to_string(iter->second));
```

可以看到：

| 下发字段 | 来源 |
| --- | --- |
| `taskid` | `actions0[0]` |
| `imageType` | `actions0[1]` |
| `vehicleName` | `"UAV" + UAVid` |
| `resourceName` | `actions0[1]` 转字符串 |

没有根据 `Capability.id`、`Capability.name`、`Capability.vehicleName` 或 `Capability.status` 查找真实资源。

最终 UDP 消息格式：

```text
taskid#imageType#UAVid
```

这只是模型动作的封装，不是基于能力表匹配出来的资源对象。

## 8. 哪些能力代码当前只是形式上存在

### 8.1 Capability

当前用途：

```text
从 sensors.txt 读取
打印 show()
```

没有用于：

```text
筛选可用资源
计算能力匹配度
构造 MAPPO 输入
约束传感器动作
下发真实资源名
```

### 8.2 CapabilityNeed

当前用途：

```text
根据 obs0 构建
打印 show()
CapAdaptiveManager 检查 isBuild()
```

没有用于：

```text
和 Capability 进行匹配
传给 SelectPlugin
影响 MAPPO 动作选择
影响 dispatch
```

### 8.3 CapabilityCanUse

当前用途：

```text
全局变量存在
头文件被 include
旧 MCTS 接口引用
```

没有用于当前主流程。

### 8.4 CapabilityAllocated

当前确实使用了。

但它保存的是 MAPPO 返回动作：

```text
actions0[0] -> actions0[1]
```

不是能力匹配算法输出的真实资源分配。

因此它是“分配结果容器”被使用了，但不是“能力系统”真正参与决策。

## 9. 评估插件本来应该使用能力，但当前被注释

`plugins/assess/AssessPlugin.cpp` 设计上会遍历 `Capability`：

```cpp
for (int i = 0; i < capabilities.size(); ++i) {
    Capability* cur = capabilities[i];
    const char* FuncName = models[cur->getName()].c_str();
    ...
    level.push_back(v);
    cur->setLevel(level);
}
```

如果启用，它会根据环境条件调用 Python 的 `assessment.py`，更新能力等级。

但在 `CapAdaptiveManager.cpp` 中，评估插件加载和调用代码整体被注释：

```cpp
/*
PluginHandler ph = NULL;
...
bool res = std::dynamic_pointer_cast<AssessAPI>(plug)->assess(resourceCapTB, curEnv);
...
*/
```

所以当前运行时没有这一步。

## 10. 旧 MCTS 选择本来应该使用能力，但当前没有调用

`plugins/select/readme.md` 和 `MTCTS.h` 中保留了旧接口思路：

```cpp
MCTSTree::Select(resourceCapCanUseTB, capNeedTB)
```

这条路径会使用：

```text
CapabilityCanUse
CapabilityNeed
```

但当前 `selectPlugin.cpp` 没有调用 `MCTSTree::Select()`，而是调用 Python MAPPO。

因此旧能力匹配路径已经被替换掉。

## 11. 判断结论

当前代码中“能力”的使用程度如下：

| 能力环节 | 当前是否执行 | 是否影响决策 |
| --- | --- | --- |
| 读取 `sensors.txt` | 是 | 否 |
| 构建 `Capability` | 是 | 否 |
| 打印能力属性 | 是 | 否 |
| 构建 `CapabilityNeed` | 是 | 基本否，仅检查是否 build |
| 评估插件更新能力等级 | 否 | 否 |
| 构建 `CapabilityCanUse` | 否 | 否 |
| 基于能力进行匹配/选择 | 否 | 否 |
| MAPPO 根据 `obs0` 选择动作 | 是 | 是 |
| `CapabilityAllocated` 封装动作结果 | 是 | 是，但封装的是动作，不是真实能力匹配结果 |
| dispatch 下发结果 | 是 | 是 |

最终结论：

```text
当前 i-ssros 没有真正用上能力系统做决策。
它只是读取和打印了能力配置，并保留了能力相关数据结构。
实际决策由 MAPPO 根据 obs0 和固定 action mask 完成。
```

## 12. 如果希望真正用上能力，应该怎么改

至少需要让能力数据进入决策链路。可以有两种方向。

### 方案 A：让能力表参与动作掩码

这是改动较小的方式。

当前传感器动作掩码写死：

```cpp
vector<float> sensors = {1, 1, 1, 0};
```

可以改为根据 `resourceCapTB` 动态生成：

```text
如果某类传感器不存在或 status=false，则 mask=0
如果当前 UAV 没有该资源，则 mask=0
如果 power 不足或 level 不满足，则 mask=0
```

这样 MAPPO 至少不会选择不可用能力。

### 方案 B：把能力特征加入 obs

当前 `obs` 只来自 `obs0`：

```cpp
obs[0].push_back(obs0[i] - '0');
```

可以把能力特征也拼进去，例如：

```text
每类资源是否可用
能力等级 level
功耗 power
分辨率/视场角编码
当前 UAV 是否拥有该能力
```

但这种方式要求重新训练 MAPPO，因为 actor 的输入维度会变化。

### 方案 C：恢复评估插件 + 能力匹配

恢复旧链路：

```text
Capability
    -> AssessPlugin 根据环境更新 level
    -> CapabilityCanUse
    -> Select/MCTS 或 MAPPO
    -> CapabilityAllocated
```

这需要恢复 `CapAdaptiveManager.cpp` 中被注释的评估插件逻辑，并明确 `CapabilityCanUse` 如何生成。

## 13. 推荐判断

如果你担心“能力代码只是摆设”，这个担心是合理的。

当前最准确的描述是：

```text
项目有能力建模代码，但当前在线决策链路没有真正使用能力模型。
能力配置文件 sensors.txt 对最终动作没有实际约束。
```

如果论文、汇报或验收里需要强调“基于能力的自适应调度”，当前代码证据是不充分的。至少应该把 `resourceCapTB` 用于构造 `available_actions`，或者把能力特征加入 MAPPO 输入，并重新训练模型。
