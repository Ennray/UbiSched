# iS2ROS 网络架构分析文档

本文档详细说明了 iS2ROS 项目中所有涉及的 IP 地址、端口及其在系统中的具体功能角色。

## 1. 核心数据流向图
系统采用 **“状态输入 -> 智能决策 -> 指令分发”** 的网络化运作模式：
1.  **AirSim/外部服务器** --(UDP)--> **IROS (接收)**
2.  **IROS (C++)** --(Socket)--> **Python RL Bridge** (进行智能匹配)
3.  **IROS (分发)** --(UDP)--> **Windows宿主机/控制台** (执行指令)

---

## 2. IP 地址功能详解

| IP 地址 | 组件 | 功能描述 |
| :--- | :--- | :--- |
| **192.168.137.1** | `CapDispatchManager` | **指令分发目标**。通常是 Windows 宿主机的 IP（ICS 网络范围）。IROS 将无人机的任务分配结果通过 UDP 发送到此地址。 |
| **127.0.0.1** | `connect_to_sim.py` | **本地回路地址**。用于 C++ 插件与本地运行的 Python 强化学习模型进行高速进程间通信。 |

---

## 3. 端口号功能详解

### 无人机实例监听端口 (UDP)
用于接收来自仿真环境（如 AirSim 脚本）的传感器数据和环境状态。
- **范围**: `8888` - `8892`
- **分配规则**: 
  - UAV1: `8888`
  - UAV2: `8889`
  - ...
  - UAV5: `8892`
- **代码实现**: `ContextRenewManager::serverGetPosData`

### 智能决策桥接端口 (TCP)
用于 C++ 端的动作选择插件（`libselect.so`）与 Python 推理脚本（`new.py`）之间的通信。
- **端口**: `65432`
- **代码实现**: `light_mappo-main/train/connect_to_sim.py`

### 外部指令分发端口 (UDP)
系统决策完成后，将“能力分配结果”回传给 Windows 端的端口。
- **基准端口**: `9999`
- **偏移规则**: `DEST_PORT - UAVid + 1`
  - 例如 UAV1 发送到 `9999`，UAV2 发送到 `9998`。
- **代码实现**: `CapDispatchManager.cpp` (L18, L67)

---

## 4. 关键配置修改指南

如果您需要将系统部署到不同的网络环境，请按以下顺序修改：
1.  **修改分发 IP**: 编辑 `iSSROS/core/CapDispatchManager.cpp` 中的 `DSET_IP_ADDRESS`。
2.  **多机部署**: 若多架无人机分布在不同板卡，请修改 `run_5_iros.sh` 中的启动参数，并确保 UDP 端口在防火墙中开启。
