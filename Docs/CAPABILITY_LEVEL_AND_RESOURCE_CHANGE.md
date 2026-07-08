# 能力等级、能力变化和 MAPPO 可用资源判断说明

本文说明当前 `i-ssros` 中“能力等级”字段原本的用途，以及在评估插件没有启用的情况下，系统实际如何判断能力变化、资源变化和 MAPPO 可用动作变化。

结论先说明：当前运行链路里，能力等级会从 `sensors.txt` 读入 `Capability.level`，但没有进入 MAPPO 的观测或动作掩码。评估插件 `AssessPlugin` 原本可以根据环境变化更新能力等级，但该插件调用代码目前在 `CapAdaptiveManager.cpp` 中被整段注释。因此当前 MAPPO 并不能根据能力等级判断资源变化，它实际只根据 `obs0` 构造出来的任务掩码和固定传感器掩码 `[1,1,1,0]` 做动作选择。

## 1. 能力等级是什么

能力等级字段位于 `iSSROS/sensors.txt`：

```text
# id|name|status|type|vehicleName|power|resolution|fov|level|position
1|EOCap|1|0|UAV1|2.5|1920x1080|87.3|70,50,60|10.0,20.0,30.0
2|IRCap|1|0|UAV1|3.0|640x512|90.0|60,55,65|15.0,25.0,35.0
3|EOCap|1|0|UAV2|2.8|1280x720|85.5|65,60,70|20.0,30.0,40.0
4|IRCap|1|0|UAV2|3.0|640x512|90.0|60,55,65|15.0,25.0,35.0
```

其中 `level` 是一个多维能力等级数组，例如：

```text
70,50,60
```

代码中对应的数据结构是：

- `iSSROS/Cap/Capability.h`
- `iSSROS/Cap/Capability.cpp`

核心字段：

```cpp
vector<float> level;
bool status;
Parameter parameter;
Position position;
string vehicleName;
float power;
```

从字段设计看，`level` 应该用于描述某个资源在不同维度上的能力水平。例如 EO 可见光能力、IR 红外能力在不同环境或不同任务指标上的性能等级。它和 `power`、`status`、`position` 一起，本来应该用于判断某个资源是否适合某个任务。

## 2. 能力等级在哪里读入

能力表读取入口是：

```text
iSSROS/CapInterface/CapInterfaceManager.cpp
```

函数：

```cpp
vector<Capability*> CapInterfaceManager::getCapabilityFromTxt(const char* filePath) const
```

它会从 `sensors.txt` 解析：

- `id`
- `name`
- `status`
- `type`
- `vehicleName`
- `power`
- `resolution`
- `fov`
- `level`
- `position`

然后通过 `CapabilityBuilder` 构造 `Capability`：

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

所以能力等级不是完全没读，它确实进入了 `resourceCapTB`。

主流程中读取位置在：

```text
iSSROS/CapEngine.cpp
```

启动时：

```cpp
resourceCapTB = CIM->getCapabilityFromTxt("./sensors.txt");
resourceCapTBReady = true;
```

需求变化时也会重新读一次：

```cpp
resourceCapTB = CIM->getCapabilityFromTxt("./sensors.txt");
resourceCapTBReady = true;
```

但是这只是把静态文件内容重新读入内存，不等于 MAPPO 已经使用了这些能力等级。

## 3. 评估插件原本打算怎么更新能力等级

评估插件在：

```text
plugins/assess/AssessPlugin.cpp
iSSROS/assessment.py
```

`AssessPlugin::assess()` 的逻辑是：

1. 根据能力名称选择评估函数。

```cpp
models["IRCap"] = "irAssess";
models["RGBCap"] = "eoAssess";
models["EOCap"] = "eoAssess";
```

2. 从当前环境 `curEnv` 中读取环境信息。

```cpp
curEnv->getLight()
curEnv->getWeather().getFog()
curEnv->getWeather().getRain()
curEnv->getWeather().getDust()
```

3. 调用 Python 模型。

```cpp
pModule = PyImport_ImportModule("assessment");
pFunc = PyObject_GetAttrString(pModule, FuncName);
pRet = PyObject_CallObject(pFunc, pArgs);
```

4. `assessment.py` 中根据 EO/IR 模型预测新的能力值。

```python
def eoAssess(light, fog, rain, dust):
    xtest = np.array([rain, fog, light])
    loaded_model1 = joblib.load('../eomodel.dat')
    y_predict_eo = loaded_model1.predict(xtest)
    return y_pre_eo

def irAssess(light, fog, rain, dust):
    xtest = np.array([rain, fog, light])
    loaded_model2 = joblib.load('../irmodel.dat')
    y_predict_ir = loaded_model2.predict(xtest)
    return y_pre_ir
```

5. 把预测结果追加到 `Capability.level`。

```cpp
vector<float> level = cur->getLevel();
for (int j = 0; j < size; ++j) {
    float v = 0.0;
    PyArg_Parse(pResVal, "f", &v);
    level.push_back(v);
}
cur->setLevel(level);
```

注意这里是 `push_back`，不是覆盖原来的 level。也就是说，如果评估插件被调用，能力等级会从 `sensors.txt` 中的静态等级继续追加评估模型输出值。

## 4. 为什么当前没有更新能力等级

当前主流程没有真正调用评估插件。

相关代码在：

```text
iSSROS/core/CapAdaptiveManager.cpp
```

里面保留了 `assessSearchPaths` 和加载 `libAssessPlugin.so` 的代码，但真正调用评估插件的部分在 `/* ... */` 注释块里。

因此当前实际运行时只做了选择插件：

```cpp
PluginHandler ph2 = NULL;
// 加载 libselect.so
...
std::dynamic_pointer_cast<SelectAPI>(plug)->select(...)
```

没有执行：

```cpp
std::dynamic_pointer_cast<AssessAPI>(plug)->assess(resourceCapTB, curEnv);
```

所以：

- `assessment.py` 不会被调用。
- `eomodel.dat` / `irmodel.dat` 不会参与当前流程。
- `Capability.level` 不会基于环境变化更新。
- `resourceCapCanUseTB` 也不会由评估结果生成。

## 5. 如果评估插件没有更新能力等级，系统如何判断能力变化

当前代码里没有形成完整的“能力变化判断”。

实际发生的是：

1. `ContextRenewManager::serverGetEnvData()` 接收 UDP 字符串。

```cpp
obs0 = buffer;
startAssess = true;
```

2. `CapEngine` 等待 `startAssess == true`。

```cpp
while (!(startAssess)) {
    sleep(1);
}
```

3. 收到触发后，重新构建能力需求。

```cpp
CNM->run();
```

4. 调用 MAPPO 选择。

```cpp
CAM->run();
```

也就是说，当前系统把“收到新的 `obs0`”当成一次调度触发。它并没有比较新旧 `Capability.level`，也没有根据环境模型重新计算能力下降或能力提升。

代码里虽然有：

```cpp
if (CNM->isModified()) {
    resourceCapTB = CIM->getCapabilityFromTxt("./sensors.txt");
}
```

但 `CapNeedManager::run()` 当前每次都是根据 `obs0` 重建需求，`isModified()` 并不是一个可靠的能力变化判断机制。即使重新读 `sensors.txt`，也只是重新读取静态文件，不会根据实时环境自动改变等级。

因此目前所谓“能力变化”更准确地说是“外部输入 obs0 变化触发一次重新选择”，不是“资源能力等级发生变化后驱动重新选择”。

## 6. MAPPO 如何判断可用资源变化

当前 MAPPO 不判断 `resourceCapTB` 的变化，也不读取 `Capability.level`。

在线运行时，`CapAdaptiveManager.cpp` 直接构造 MAPPO 输入：

```cpp
vector<vector<float>> obs;
obs.push_back(vector<float>());
for (int i = 0; i < obs0.length(); i++) {
    obs[0].push_back(obs0[i] - '0');
}
```

任务可用性来自 `obs0[1:]`：

```cpp
vector<float> tasks;
for (int i = 1; i < obs0.length(); i++) {
    if (obs0[i] == '0') tasks.push_back(0);
    else tasks.push_back(1);
}
```

传感器可用性是硬编码：

```cpp
vector<float> sensors = {1, 1, 1, 0};
```

最终传给 MAPPO 的 `available_actions` 是：

```cpp
available_actions[0].push_back(tasks);
available_actions[0].push_back(sensors);
```

所以 MAPPO 当前判断“可用资源变化”的依据只有：

- `obs0` 变化导致观测 `obs` 变化。
- `obs0[1:]` 变化导致任务掩码 `tasks` 变化。
- 传感器掩码始终是 `[1,1,1,0]`，不会随能力表变化。

这意味着：

- 某个传感器 `status=0`，MAPPO 目前不知道。
- 某个传感器能力等级下降，MAPPO 目前不知道。
- 某个传感器功耗过高，MAPPO 目前不知道。
- 某个 UAV 位置变化，MAPPO 目前不知道。
- `sensors.txt` 中 `level` 改了，除非你另外把它编码进 `obs` 或 `available_actions`，否则 MAPPO 不会使用。

## 7. 当前可用资源变化的真实来源

当前代码中“可用资源变化”实际分成两类：

### 7.1 任务可用性变化

这个是有的。

在线阶段由 `obs0[1:]` 决定：

```text
obs0 某位为 0 -> 对应任务不可选
obs0 某位非 0 -> 对应任务可选
```

训练阶段由 `EnvCore.step()` 决定：

```cpp
任务完成后 last_obs[task] = 0
available_actions[j][0][task_id] = 0
```

所以当前 MAPPO 对“哪些任务还能选”是能感知的。

### 7.2 传感器/资源可用性变化

这个当前基本没有。

训练阶段：

```python
np.array([1, 1, 1, 0])
```

在线阶段：

```cpp
vector<float> sensors = {1, 1, 1, 0};
```

两边都是固定值。也就是说，MAPPO 当前没有动态感知“哪类传感器还能用”。

## 8. 能力等级原本应该如何参与决策

从代码结构看，原本更完整的设计应该是：

```text
sensors.txt
  -> resourceCapTB: 原始能力表
  -> AssessPlugin 根据环境 curEnv 更新 Capability.level
  -> 生成 resourceCapCanUseTB 或更新可用资源判断
  -> SelectPlugin 根据能力需求 capNeedTB 和可用能力选择资源
  -> CapabilityAllocated
  -> Dispatch
```

但当前 MAPPO 版本绕过了这个旧链路：

```text
obs0
  -> obs
  -> tasks mask
  -> fixed sensors mask [1,1,1,0]
  -> MAPPO actor
  -> [task_idx, sensor_idx]
  -> CapabilityAllocated
  -> Dispatch
```

因此能力等级目前更像“被读入但没有参与决策的数据”。

## 9. 当前代码中的几个关键问题

1. 评估插件未启用。
   - `AssessPlugin::assess()` 不会运行。
   - `Capability.level` 不会根据环境更新。

2. `curEnv` 当前没有被实际更新。
   - `ContextRenewManager::serverGetEnvData()` 中原本解析天气、光照并写入 `curEnv` 的代码也被注释掉了。
   - 即使启用评估插件，也需要先恢复环境对象更新逻辑，否则评估没有可靠输入。

3. 传感器掩码是硬编码。
   - 在线：`vector<float> sensors = {1,1,1,0}`。
   - 训练：`np.array([1,1,1,0])`。

4. 能力等级没有进入 MAPPO 观测。
   - `obs` 只来自 `obs0` 字符串。
   - `level`、`power`、`status`、`position` 都没有编码进去。

5. 能力可用表 `CapabilityCanUse` 没有进入当前选择链路。
   - 数据结构存在。
   - 但当前 MAPPO 选择插件不依赖它。

## 10. 回答这几个问题

### 能力等级是用来干啥的？

从设计上，它是描述资源能力强弱的多维指标，应该用于判断某个传感器或资源在当前环境下是否适合执行某个任务。比如可见光在低光、雨雾下能力可能下降，红外在某些环境下能力可能更合适。

但在当前运行代码里，它只被读入和打印，没有真正影响 MAPPO 决策。

### 评估插件没有更新能力等级时，如何判断能力变化？

当前没有真正判断能力变化。系统只是收到新的 `obs0` 后触发一次重新调度。这个触发代表“外部状态变了”，但不是代码内部根据能力等级变化判断出来的。

### MAPPO 如何判断可用资源变化？

MAPPO 当前只通过 `available_actions` 判断可用性：

- 第一组 `tasks`：由 `obs0[1:]` 生成，表示任务是否可选。
- 第二组 `sensors`：固定 `[1,1,1,0]`，表示前三类传感器可选，第四类不可选。

所以 MAPPO 当前能判断任务可用性变化，但不能判断传感器能力变化或真实资源变化。

## 11. 如果要让能力等级真正生效

建议按这个方向改：

1. 恢复环境更新。
   - 在 `ContextRenewManager::serverGetEnvData()` 中解析光照、雾、雨、尘等环境数据，更新 `curEnv`。

2. 恢复评估插件调用。
   - 在 `CapAdaptiveManager.cpp` 中启用 `AssessPlugin::assess(resourceCapTB, curEnv)`。

3. 明确评估结果如何影响可用资源。
   - 不建议只把新评估值 `push_back` 到 `level`。
   - 更清晰的做法是覆盖或单独保存 `currentLevel`。

4. 把能力结果接入 MAPPO。
   - 简单方式：根据 `status` 和 `level` 生成传感器掩码，比如能力低于阈值就把对应 sensor mask 置 0。
   - 更完整方式：把 `level`、`power`、`status`、`position` 编入 MAPPO 的 `obs`，并同步修改训练环境，让训练和在线输入一致。

5. 保持训练和在线一致。
   - 如果在线根据能力等级改变 `available_actions`，训练环境也必须加入同样逻辑，否则模型训练时没见过这种变化，推理时效果不稳定。

当前最小改造路径是：先用能力等级生成 `sensors` 掩码，而不是固定写死 `[1,1,1,0]`。这样 MAPPO 至少能通过动作掩码知道哪些传感器当前不可用。
