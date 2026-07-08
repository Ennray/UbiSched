# iS2ROS 系统架构分析

## 1. 总体设计
iS2ROS 是一个基于 **C++ 核心调度 + 插件化扩展 + Python 智能决策** 的异构分布式系统。它主要用于无人机（UAV）能力的动态评估与调度。

## 2. 核心模块划分

### 2.1 C++ 核心引擎 (`iSSROS/`)
- **`CapEngine`**: 系统的动力源，负责多线程管理和调度循环。
- **`core/` (管理器层)**:
  - `CapNeedManager`: 管理任务需求。
  - `ContextRenewManager`: 接收外部（AirSim）传感器数据，更新环境上下文。
  - `CapAdaptiveManager`: **核心逻辑中枢**，协调插件加载与决策调用。
  - `CapDispatchManager`: 将决策结果通过网络下发至执行端。
- **`plugin/`**: 实现了一套轻量级的 C++ 插件框架，支持运行时动态加载 `.so` 库。

### 2.2 插件层 (`plugins/`)
- **评估插件 (`assess/`)**: 计算无人机当前状态与任务的匹配度。
- **选择插件 (`select/`)**: 
  - 核心功能：动作选择（Action Selection）。
  - 实现方式：通过 **Python C API** 桥接至深度强化学习模型。

### 2.3 算法层 (`light_mappo-transformer/`)
- 基于 MAPPO（Multi-Agent PPO）算法。
- 提供 `new.py` 推理接口，处理来自 C++ 的观测向量（obs）并返回动作索引。

## 3. 数据流转逻辑
1.  **输入**: 外部仿真器通过 UDP 8888-8892 端口发送环境 JSON/字符串。
2.  **处理**: `ContextRenewManager` 解析数据 -> `CapAdaptiveManager` 加载 `libselect.so`。
3.  **决策**: `libselect.so` 调用 Python 环境加载神经网络权重 -> 返回最优动作。
4.  **输出**: `CapDispatchManager` 将任务指令发送至 `192.168.137.1:9999`。
