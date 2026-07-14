# AirSim、iS2ROS 与 UbiSched 运行流程说明

## 一、文档目的

本文说明以下三部分之间的关系：

- AirSim 仿真程序。
- 原 iS2ROS 调度系统。
- 当前新增的 UbiSched 图匹配与规则调度模块。

重点回答：

1. 原系统需要启动哪些程序。
2. AirSim Python 脚本如何连接 iS2ROS。
3. 当前 UbiSched 已经运行到哪一步。
4. 新旧系统的流程有什么相同和不同。
5. 后续 AirSim-UbiSched Bridge 应该做什么。

## 二、三个程序的职责

### 2.1 AirSim

AirSim 是仿真环境，负责：

- 模拟 UAV 飞行。
- 提供位置、图像和环境状态。
- 接收 Python API 发出的飞行和采图指令。

AirSim 本身不负责任务资源调度。

### 2.2 AirSim Python 控制脚本

Python 脚本处于 AirSim 和调度系统之间，负责：

- 通过 AirSim Python API 控制 UAV。
- 从 AirSim 读取位置、图像和天气信息。
- 将任务或环境状态发送给调度端。
- 接收调度结果。
- 根据调度结果选择任务、传感器和 UAV 行为。

原项目中与该流程最接近的脚本是：

```text
F:\工作\173\交接工作\交接工作\代码\Airsim相关代码\
airsim-python\backup\connect_to_MARL.py
```

另一套多 UAV 和天气控制代码位于：

```text
F:\工作\173\交接工作\交接工作\代码\Airsim相关代码\
airsim-python\airsimCode.py
```

### 2.3 调度程序

调度程序负责决定：

```text
哪个任务分配给哪个传感器或计算资源
```

原系统的调度端是常驻 C++ 进程 `IROS`，内部调用原 MAPPO。

当前 UbiSched 已经实现了独立的任务图、资源图、匹配矩阵、动作掩码、
状态更新和自动规则调度，但还没有实现 AirSim 网络 Bridge。

## 三、原 iS2ROS 完整运行流程

原系统的结构如下：

```text
AirSim
  ↑↓ AirSim Python API
connect_to_MARL.py
  ↑↓ UDP
IROS 常驻进程
  ↓
选择插件
  ↓
原 MAPPO 在线推理
```

原系统不能只运行 AirSim Python 脚本。`IROS` 必须同时运行并监听 UDP。

### 3.1 启动 IROS

UAV1：

```bash
./IROS 8888 1
```

参数含义：

| 参数 | 含义 |
| --- | --- |
| `8888` | IROS 接收外部状态的 UDP 端口 |
| `1` | UAV 编号，从 1 开始 |

### 3.2 AirSim Python 发送状态

`connect_to_MARL.py` 中的核心发送代码是：

```python
require.sendto(send_msg.encode("UTF-8"), ("127.0.0.1", 8888))
```

原始 `send_msg` 类似：

```text
011111
```

它是旧 MAPPO 使用的字符级观测，不是 TaskGraph 或 ResourceGraph。

当前 IROS 接收端还支持以下格式：

```text
time#light#fog#rain#dust#obs
```

收到消息后，IROS 会：

1. 更新环境状态和 `obs0`。
2. 设置 `startAssess = true`。
3. 触发一次需求构建和 MAPPO 选择。
4. 将选择结果通过 UDP 发回 AirSim Python。

### 3.3 IROS 返回调度结果

返回消息格式为：

```text
task_id#sensor_id#UAV_name
```

例如：

```text
0#1#UAV1
```

表示将任务 0 分配给 UAV1 的 1 号传感器。

目标 IP 从 UbiSched 仓库根目录的 `config.ini` 读取：

```ini
[network]
DEST_IP_ADDRESS=10.70.250.195
```

该地址应设置为运行 AirSim Python 脚本的电脑 IP。

## 四、多 UAV 端口对应关系

IROS 的输入端口由启动参数指定，返回端口按以下公式计算：

```text
返回端口 = 9999 - UAV_ID + 1
```

对应关系：

| UAV | IROS 启动命令 | 状态输入端口 | 结果返回端口 |
| --- | --- | --- | --- |
| UAV1 | `./IROS 8888 1` | 8888 | 9999 |
| UAV2 | `./IROS 8889 2` | 8889 | 9998 |
| UAV3 | `./IROS 8890 3` | 8890 | 9997 |
| UAV4 | `./IROS 8891 4` | 8891 | 9996 |
| UAV5 | `./IROS 8892 5` | 8892 | 9995 |

每个 IROS 实例代表一个 UAV 调度节点。

## 五、原系统的正确启动顺序

```text
1. 启动 AirSim 场景
2. 启动 IROS 常驻进程
3. 启动 AirSim Python 控制脚本
4. Python 向 IROS 发送状态
5. IROS 调用原 MAPPO
6. IROS 返回任务和传感器选择
7. Python 控制 AirSim 中的 UAV 执行
```

单 UAV 示例：

```text
终端 1（Linux 或板卡）：
./IROS 8888 1

终端 2（AirSim 所在电脑）：
python connect_to_MARL.py
```

如果 AirSim Python 与 IROS 不在同一台设备或同一网络空间，
`127.0.0.1` 必须改为 IROS 所在设备的实际 IP。

## 六、电脑运行和板卡运行的区别

原 iS2ROS 可以烧录到板卡，也可以在电脑 Linux 环境中运行。

两种方式的调度逻辑相同，区别主要是 IP 地址：

### 6.1 同一台 Linux 电脑

```text
AirSim Python -> 127.0.0.1:8888 -> IROS
IROS -> 127.0.0.1:9999 -> AirSim Python
```

### 6.2 AirSim 在 Windows，IROS 在板卡

```text
AirSim Python -> 板卡IP:8888 -> IROS
IROS -> Windows电脑IP:9999 -> AirSim Python
```

### 6.3 AirSim 在 Windows，IROS 在 WSL

普通 WSL2 与 Windows 可能不共享 UDP localhost。此时通常需要使用 WSL 的实际
IP，或者启用支持 localhost/UDP 的镜像网络模式，不能直接假定
`127.0.0.1:8888` 一定可达。

还需要允许防火墙放行对应 UDP 端口。

## 七、当前 AirSim 脚本的注意事项

### 7.1 connect_to_MARL.py

该脚本最符合原任务调度闭环：

```text
发送 obs -> 等待调度结果 -> 执行任务 -> 更新 obs -> 再次发送
```

但它当前同时写有：

```python
host = "192.168.137.1"
require.sendto(..., ("127.0.0.1", 8888))
```

运行前必须根据实际部署修改发送 IP 和监听 IP。

### 7.2 airsimCode.py

该脚本主要用于多 UAV、天气和图像采集，当前硬编码：

```python
server_address = ("192.168.1.7", 8888)
server_address2 = ("192.168.1.7", 8889)
```

它发送到 8888 的天气消息通常只有 5 段：

```text
time#light#fog#rain#dust
```

这种消息会触发 IROS，但不会更新第 6 段 `obs0`。因此复现原 MAPPO 任务闭环时，
优先使用 `connect_to_MARL.py`，不要把两个脚本的用途混在一起。

## 八、当前 UbiSched 已完成的流程

当前新模块已经形成以下独立闭环：

```text
YAML 配置
  ↓
TaskGraph + ResourceGraph
  ↓
MatchMatrix
  ↓
ActionMask
  ↓
RuleBasedScheduler 自动选择最高分动作
  ↓
AssignmentExecutor 更新任务、资源、时间和能量
  ↓
重新匹配，直到任务图完成
```

运行：

```powershell
cd "F:\工作\173\代码\UbiSched"
python scripts/demo_rule_based_scheduling.py
```

当前示例输出：

```text
status: completed
assign(detect_target, uav_1_rgb_sensor)
assign(classify_target, uav_2_compute)
makespan: 9.25
total_energy: 412.0
deadline_met_rate: 1.0
```

运行全部测试：

```powershell
python -m pytest tests
```

当前结果：

```text
22 passed
```

## 九、新旧系统的相同点

外部运行思路基本相同，都需要仿真端和调度端：

```text
仿真端产生状态
    ↓
调度端选择任务资源
    ↓
仿真端执行选择结果
```

因此未来 UbiSched 接入 AirSim 后，仍然需要分别启动 AirSim、调度 Bridge 和
AirSim Python 控制程序。

## 十、新旧系统的不同点

| 对比项 | 原 iS2ROS | 当前 UbiSched |
| --- | --- | --- |
| 任务输入 | `obs0` 字符串 | TaskGraph |
| 资源输入 | 固定传感器编号和旧能力表 | ResourceGraph |
| 任务依赖 | 没有结构化依赖图 | precedence 边 |
| 资源属性 | 未真正进入 MAPPO | 质量、位置、能量、CPU、链路、负载等 |
| 动作掩码 | 任务状态加固定传感器 mask | MatchMatrix.feasible 动态生成 |
| 当前选择方法 | 原 MAPPO | 最高 match_score 规则调度 |
| 状态执行 | 依赖外部 obs 更新 | AssignmentExecutor 内部闭环 |
| AirSim 网络接入 | 已有旧 UDP 脚本 | 尚未实现 Bridge |

## 十一、当前不能做什么

当前 UbiSched 还不能只等待 AirSim 脚本自动连接，因为它目前：

- 不监听 UDP 8888。
- 不解析 AirSim 实时状态。
- 不向 9999 返回调度结果。
- 不会在 AirSim 启动后自动运行。
- 运行 demo 后会完成示例任务并退出，不是常驻服务。

因此当前新旧链路仍然是独立的：

```text
旧链路：
AirSim Python <-> IROS <-> 原 MAPPO

新链路：
YAML -> UbiSched -> 规则调度结果
```

## 十二、下一步：AirSim-UbiSched Bridge

下一阶段应新增常驻 Bridge：

```text
AirSim Python
    ↓ 结构化状态
AirSim-UbiSched Bridge
    ↓
更新 TaskGraph 和 ResourceGraph
    ↓
生成 MatchMatrix 和 ActionMask
    ↓
规则调度器，后续替换为 MAPPO
    ↓
返回 assign(subtask_id, resource_id)
    ↓
AirSim Python 执行任务和采图
```

建议使用 JSON 协议，而不是继续扩展旧的 `011111` 字符串。JSON 至少需要表达：

- 当前时间。
- 子任务 ID、状态、位置和 deadline。
- UAV 和资源 ID。
- 传感器模态与质量。
- UAV 或资源位置。
- CPU、队列和链路速率。
- 剩余能量和占用状态。

Bridge 可以同时提供一个旧协议兼容模式，用于验证原 AirSim Python 脚本和
UDP 端口是否正常，但新的图匹配数据不应继续压缩成字符级 `obs0`。
