# iS2ROS 代码说明

本文档面向代码阅读和二次开发，解释当前仓库中主程序、插件、强化学习推理模块之间的关系，以及一次完整调度流程的数据如何流转。

## 1. 项目整体结构

项目由三部分组成：

| 路径 | 作用 |
| --- | --- |
| `iSSROS/` | C++ 主程序。负责接收外部状态、构建能力需求、加载插件、下发调度结果。 |
| `plugins/` | C++ 动态插件。当前包含评估插件 `assess` 和选择插件 `select`。 |
| `light_mappo-transformer/` | Python 强化学习模型代码。选择插件通过 Python C API 调用其中的推理函数。 |
| `Docs/` | 项目说明文档。 |
| `文档/` | 原始 PDF 资料。 |
| `Makefile` | 统一编译入口，支持 x86 编译、ARM 交叉编译和部署打包。 |
| `config.ini` | 网络目标地址配置，目前用于调度结果发送目标 IP。 |

整体设计可以概括为：

```text
外部状态输入 UDP
    -> ContextRenewManager 更新 obs0
    -> CapEngine 触发能力需求构建和自适应决策
    -> CapAdaptiveManager 动态加载 libselect.so
    -> SelectPlugin 调用 Python actor_inference
    -> CapDispatchManager 通过 UDP 下发调度结果
```

## 2. 程序入口和线程模型

入口文件是 `iSSROS/main.cpp`。

程序启动参数：

```bash
./IROS <listening_port> <UAVid>
```

例如：

```bash
./IROS 8888 1
```

启动后会设置两个全局值：

| 全局变量 | 来源 | 含义 |
| --- | --- | --- |
| `listening_port` | 命令行第 1 个参数 | 当前 IROS 实例监听外部状态的 UDP 端口。 |
| `UAVid` | 命令行第 2 个参数 | 当前无人机编号，从 1 开始。 |

`main.cpp` 里主要启动两个线程：

| 线程 | 调用函数 | 作用 |
| --- | --- | --- |
| 环境接收线程 | `ContextRenewManager::serverGetEnvData` | 监听 UDP，接收外部状态字符串。 |
| 能力引擎线程 | `CapEngine::run` | 执行需求构建、插件选择、结果下发。 |

代码里定义了 `threadCount=3`，但实际只初始化了 `t[0]` 和 `t[1]`。如果保持当前写法，`for` 循环会对 `t[2]` 调用 `join()`，这里存在运行风险。应将 `threadCount` 改为 2，或者恢复第三个线程初始化。

## 3. 全局状态

全局变量集中定义在 `iSSROS/Utils/Global.cpp`。

关键变量如下：

| 变量 | 作用 |
| --- | --- |
| `obs0` | 当前外部状态字符串，默认值为 `"111101"`。 |
| `weathernums` | 前几个字符被视为天气/环境字段，当前值为 `1`。 |
| `startAssess` | UDP 收到新状态后置为 `true`，驱动能力引擎执行一次评估/选择。 |
| `startSelect` | 位置数据选择触发标记，目前相关线程被注释，主流程中未实际依赖。 |
| `capNeedTB` | 当前能力需求表。 |
| `resourceCapTB` | 当前可用资源能力表，从 `sensors.txt` 读取。 |
| `resourceCapAllocatedTB` | 选择插件输出后的资源分配结果。 |
| `curEnv` | 环境对象。当前评估插件路径保留，但主流程里评估逻辑被注释，实际使用较少。 |
| `UAVid` | 当前无人机编号。 |
| `listening_port` | 当前 UDP 监听端口。 |

这些变量是跨线程共享的，但当前代码没有对 `obs0`、`startAssess` 等状态做完整同步保护。后续如果提高并发稳定性，需要补充锁或原子变量。

## 4. 状态接收：ContextRenewManager

文件：

```text
iSSROS/core/ContextRenewManager.cpp
```

核心函数是：

```cpp
void ContextRenewManager::serverGetEnvData()
```

它做了几件事：

1. 使用 `listening_port` 创建 UDP socket。
2. 绑定到 `INADDR_ANY:<listening_port>`。
3. 循环调用 `recvfrom` 接收外部消息。
4. 收到消息后将字符串写入全局变量 `obs0`。
5. 将 `startAssess` 设置为 `true`，通知能力引擎可以执行一次选择。

当前接收缓冲区大小为 128 字节：

```cpp
char buffer[128];
```

因此输入状态字符串不能太长，否则会被截断。

## 5. 能力引擎主循环：CapEngine

文件：

```text
iSSROS/CapEngine.cpp
```

主函数是：

```cpp
void CapEngine::run()
```

流程如下：

1. 获取单例管理器：
   - `CapNeedManager`
   - `CapInterfaceManager`
   - `CapAdaptiveManager`
   - `CapDispatchManager`
2. 调用 `CapNeedManager::run()` 构建初始能力需求。
3. 从 `./sensors.txt` 读取资源能力表。
4. 进入无限循环。
5. 等待 `startAssess == true`。
6. 收到新状态后：
   - 重新构建能力需求。
   - 调用 `CapAdaptiveManager::run()` 做能力选择。
   - 调用 `CapDispatchManager::run(resourceCapAllocatedTB)` 下发结果。
   - 将 `startAssess` 和 `startSelect` 重置为 `false`。

简化伪代码：

```text
构建能力需求
读取传感器资源

while true:
    等待 startAssess
    根据 obs0 重建需求
    调用选择插件
    下发分配结果
    重置触发标记
```

## 6. 能力需求构建：CapNeedManager

文件：

```text
iSSROS/core/CapNeedManager.cpp
iSSROS/Cap/CapabilityNeed.cpp
```

`CapNeedManager::buildCapNeedTB()` 会根据 `obs0` 构建能力需求表。

关键逻辑：

```cpp
for(int i = weathernums; i < obs0.length(); i++){
    CapNeedTB->add(obs0[i] - '0', 10, 0.8);
}
```

也就是说：

| 字段 | 含义 |
| --- | --- |
| `obs0[0]` | 当前被视为环境/天气字段，不进入能力需求。 |
| `obs0[1:]` | 每个字符被转换成一个能力需求 ID。 |
| `10` | 固定持续时间。 |
| `0.8` | 固定需求等级。 |

例如 `obs0 = "111101"`，`weathernums = 1` 时，会从后 5 位构建 5 条能力需求。

`CapabilityNeed` 内部用三个数组保存需求：

| 成员 | 作用 |
| --- | --- |
| `capneedid` | 能力需求 ID。 |
| `lasttime` | 需求持续时间。 |
| `leveldemand` | 能力等级需求。 |

## 7. 资源能力读取：CapInterfaceManager

文件：

```text
iSSROS/CapInterface/CapInterfaceManager.cpp
iSSROS/sensors.txt
```

`CapInterfaceManager::getCapabilityFromTxt()` 读取 `sensors.txt`，并转换成 `Capability` 对象列表。

当前 `sensors.txt` 格式：

```text
id|name|status|type|vehicleName|power|resolution|fov|level|position
```

示例：

```text
1|EOCap|1|0|UAV1|2.5|1920x1080|87.3|70,50,60|10.0,20.0,30.0
```

解析结果会写入 `Capability`：

| 字段 | 对应对象内容 |
| --- | --- |
| `id` | 能力 ID。 |
| `name` | 能力名称，如 `EOCap`、`IRCap`。 |
| `status` | 资源是否可用。 |
| `vehicleName` | 所属无人机。 |
| `power` | 功耗。 |
| `resolution`、`fov` | 写入 `Parameter`。 |
| `level` | 多维能力等级。 |
| `position` | 写入 `Position`。 |

注意：代码读取了 `type` 字段，但当前构建 `Capability` 时没有调用 `type(...)` 写入 builder，因此 `Capability::type` 可能保持默认值。

## 8. 动态插件机制

相关文件：

```text
iSSROS/plugin/PluginImpl.h
iSSROS/plugin/PluginMgr.cpp
iSSROS/plugin/PluginMgrImpl.cpp
```

插件系统基于 Linux 动态库：

| 操作 | 实现 |
| --- | --- |
| 加载动态库 | `dlopen` |
| 获取符号 | `dlsym` |
| 卸载动态库 | `dlclose` |

每个插件都需要通过宏暴露统一入口：

```cpp
DEFINE_PLUGIN(SelectPlugin)
```

这个宏会导出 C 风格函数：

```cpp
extern "C" GetPluginFunction InitPlugin()
```

主程序加载 `.so` 后，查找符号名：

```cpp
PLUGIN_INIT_FUNCTION_NAME = "InitPlugin"
```

拿到 `InitPlugin` 后，再通过它获得实际插件对象。

## 9. 自适应决策：CapAdaptiveManager

文件：

```text
iSSROS/core/CapAdaptiveManager.cpp
```

这是当前调度决策的核心。

它的逻辑分两部分：

1. 评估插件路径保留，但实际代码被整段注释。
2. 选择插件实际启用，动态加载 `libselect.so`。

选择插件搜索路径：

```text
libselect.so
./libselect.so
../libselect.so
./plugins/select/build/libselect.so
../plugins/select/build/libselect.so
```

加载成功后：

1. 获取 `InitPlugin`。
2. 生成 `SelectPlugin` 实例。
3. 将 `obs0` 转换成 `vector<vector<float>> obs`。
4. 构造 `rnn_states`。
5. 构造 `available_actions`。
6. 调用：

```cpp
std::dynamic_pointer_cast<SelectAPI>(plug)->select(
    obs,
    rnn_states,
    available_actions,
    actions0,
    UAVid
);
```

当前 `available_actions` 由两部分组成：

```cpp
tasks:   根据 obs0[1:] 生成，字符为 '0' 则不可用，否则可用
sensors: 固定为 {1, 1, 1, 0}
```

选择插件返回 `actions0` 后，代码取前两个动作：

```cpp
res[(int)actions0[0]] = (int)actions0[1];
resourceCapAllocatedTB = new CapabilityAllocated(res);
```

也就是把动作解释成：

```text
任务 ID -> 图像/资源类型
```

## 10. 选择插件：plugins/select

主要文件：

```text
plugins/select/selectPlugin.cpp
plugins/select/selectPlugin.h
plugins/select/SelectAPI.h
plugins/select/CMakeLists.txt
```

`SelectPlugin` 同时继承：

```cpp
PluginImpl<SelectPlugin>
SelectAPI
```

其中 `SelectAPI` 定义选择接口：

```cpp
virtual bool select(
    const vector<vector<float>>& obs,
    const vector<float>& rnn_states,
    const vector<vector<vector<float>>>& available_actions,
    vector<float>& actions0,
    int UAVid
) = 0;
```

`SelectPlugin::select()` 内部使用 Python C API：

1. `Py_Initialize()` 初始化 Python 解释器。
2. 向 `sys.path` 添加多个相对路径，确保可以找到 `light_mappo-main/train/new.py`。
3. `PyImport_ImportModule("new")` 导入 Python 模块。
4. 获取 `actor_inference` 函数。
5. 将 C++ 的 `vector` 参数转换成 Python `list`。
6. 调用：

```python
actor_inference(obs, rnn_states, available_actions, UAVid)
```

7. 将 Python 返回的 list 转换回 `vector<float> actions0`。

这个插件实际把 C++ 调度系统和 Python 强化学习模型连接起来。

## 11. Python 推理入口：new.py

文件：

```text
light_mappo-transformer/light_mappo-main/train/new.py
```

核心函数：

```python
def actor_inference(obs, rnn_states, available_actions, UAVid):
```

主要步骤：

1. 读取 MAPPO 配置。
2. 创建 `MultiDiscrete([[0, 4], [0, 2]])` 环境，用于获得 observation/action space。
3. 创建 `R_Actor` 网络。
4. 根据 `UAVid` 加载对应权重：

```python
weights/5UAVs/actor_agent{UAVid-1}.pt
```

例如 `UAVid=1` 加载：

```text
actor_agent0.pt
```

5. 将模型设为 eval 模式。
6. 调用 actor 得到动作。
7. 返回动作列表。

返回值会被 C++ 解释为：

```text
[任务ID, 资源/图像类型]
```

## 12. 结果下发：CapDispatchManager

文件：

```text
iSSROS/core/CapDispatchManager.cpp
```

`CapDispatchManager::run()` 接收 `CapabilityAllocated`，将其转换为 UDP 字符串并发送给外部执行端。

目标 IP 读取顺序：

1. `config.ini`
2. `../config.ini`
3. `../../config.ini`
4. 默认 `192.168.137.1`

配置文件示例：

```ini
[network]
DEST_IP_ADDRESS=10.70.250.195
```

目标端口计算：

```cpp
target_port = DEST_PORT - UAVid + 1;
```

发送消息格式：

```text
taskid#imageType#vehicleName
```

如果有多条资源，用空格分隔：

```text
1#2#UAV1 3#1#UAV1
```

## 13. 评估插件现状

评估插件位于：

```text
plugins/assess/
```

主要文件：

```text
plugins/assess/AssessPlugin.cpp
```

它设计上会调用 Python 文件：

```text
iSSROS/assessment.py
```

根据环境光照、雾、雨、尘等条件调用不同评估函数：

| 能力名 | Python 函数 |
| --- | --- |
| `EOCap` / `RGBCap` | `eoAssess` |
| `IRCap` | `irAssess` |

但在当前 `CapAdaptiveManager.cpp` 中，评估插件加载与调用逻辑被注释，因此实际运行路径里主要走选择插件。

## 14. 编译和运行

统一入口是根目录 `Makefile`。

x86 编译：

```bash
make x86
```

会编译：

| 目标 | 输出位置 |
| --- | --- |
| 主程序 | `iSSROS/build/IROS` |
| 评估插件 | `plugins/assess/build/libAssessPlugin.so` |
| 选择插件 | `plugins/select/build/libselect.so` |

ARM 交叉编译：

```bash
make arm
```

部署打包：

```bash
make deploy
```

启动脚本：

```text
run_iros_yolo.sh
stop_iros_yolo.sh
```

`run_iros_yolo.sh` 当前会启动：

1. `./IROS 8888 1`
2. 外部 YOLOv5 推理脚本 `IR_test.py`

## 15. 当前代码需要特别注意的点

1. `main.cpp` 中 `threadCount=3`，但只创建了两个线程，第三个线程未初始化却会被 `join()`。
2. `obs0` 和 `startAssess` 是跨线程共享状态，当前没有完整同步保护。
3. `CapNeedManager::buildCapNeedTB()` 中 `struct stat buf; lastMFTime = buf.st_mtime;` 没有先调用 `stat()`，该值没有实际意义。
4. `CapabilityNeed::add(int id, int time, int demand)` 第三个参数是 `int`，但调用处传入 `0.8`，会被截断成 `0`。如果需求等级要保留小数，应把参数类型改成 `float`。
5. `CapInterfaceManager` 读取了 `type`，但构建 `Capability` 时没有写入 `type`。
6. `SelectPlugin::select()` 每次调用都会 `Py_Initialize()`，长期运行时可以考虑只初始化一次 Python 解释器。
7. `new.py` 的 `__main__` 测试调用缺少 `UAVid` 参数，直接运行测试分支会报参数错误。
8. 评估插件代码存在，但主流程中被注释，当前能力等级评估没有真正参与选择。

## 16. 一次完整运行的数据例子

假设外部给 `8888` 端口发送：

```text
111101
```

运行链路如下：

1. `ContextRenewManager` 收到字符串，写入 `obs0="111101"`，设置 `startAssess=true`。
2. `CapEngine` 发现 `startAssess=true`，开始一次调度。
3. `CapNeedManager` 跳过第 1 位环境字段，从 `11101` 构建能力需求。
4. `CapAdaptiveManager` 加载 `libselect.so`。
5. `SelectPlugin` 调用 Python `actor_inference()`。
6. `new.py` 根据 `UAVid` 加载对应 actor 权重，返回动作。
7. `CapAdaptiveManager` 将动作转成 `CapabilityAllocated`。
8. `CapDispatchManager` 发送类似如下消息：

```text
taskid#imageType#UAV1
```

这就是当前代码中从状态输入到调度结果输出的主链路。
