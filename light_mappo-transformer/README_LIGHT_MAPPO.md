# Light-MAPPO 推理模块文档

## 概述
本项目集成了 Light-MAPPO 算法的推理功能，支持从 C++ 环境中通过 Python 接口调用训练好的多智能体模型进行动作选择。

## 核心文件
- `light_mappo-main/train/new.py`: 核心推理脚本，提供 `actor_inference` 函数。
- `light_mappo-main/weights/5UAVs/`: 存放预训练模型权重文件（`.pt`）。

## 主要改进 (针对硬编码路径)

### 1. Python 推理脚本 (`new.py`)
- **动态模型路径**: 原有的绝对路径已改为基于脚本位置的相对路径。使用 `pathlib` 库自动获取项目根目录，无论项目安装在何处，均能准确定位 `weights` 文件夹。
  ```python
  project_root = Path(__file__).resolve().parents[1]
  model_path0 = project_root / "weights" / "5UAVs" / f"actor_agent{UAVid-1}.pt"
  ```

### 2. C++ 插件集成 (`selectPlugin.cpp`)
- **多级路径搜索**: 移除了硬编码的 Anaconda 用户路径。现在 C++ 插件会尝试从多个相对路径（`.`, `../`, `../../`）自动搜索并添加 Python 模块路径到 `sys.path`。
- **环境无关性**: 支持从项目根目录或 `build` 目录直接启动，无需修改源代码。

## 使用说明

### 输入参数 (actor_inference)
- `obs`: 观测数据，List 格式。
- `rnn_states`: RNN 隐藏状态。
- `available_actions`: 可用动作掩码。
- `UAVid`: 智能体 ID（从 1 开始计数）。

### 返回值
- 返回一个包含智能体动作的列表。

## 部署建议
1. 确保 Python 环境已安装 `torch`, `numpy` 和 `pathlib`。
2. 运行 IROS 时，程序会自动在 `light_mappo-transformer` 目录下寻找相关脚本。
