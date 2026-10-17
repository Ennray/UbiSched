# UbiSched 新版图调度

新版唯一命令入口是 `ubisched/__main__.py`。从项目根目录运行 `python -m ubisched`。
任务图、资源图、MAPPO 推理和执行反馈均可独立运行，不需要先启动旧能力需求管理器或旧选择插件。

## 安装与快速检查

Python 3.10 及以上。建议在单独的虚拟环境中安装。

```bash
python -m pip install -e ".[models,dev]"
python -m ubisched --help
python scripts/demo_v2_runtime.py
python -m pytest tests -q
```

演示使用 mock 执行程序，只检查软件流程。它不采集图像、不运行识别模型、不控制无人机。
演示在临时目录中运行，不覆盖正式运行数据库。新规则服务本身仅依赖 Python 标准库，模型推理需要 PyTorch。

## 启动新版

```bash
python -m ubisched serve --auto-schedule
```

默认使用任务依赖增强 Transformer 和包内 Stage 11 权重。包内旧权重只训练过 24 回合，启动时会提示它属于接口检查用权重。
它不代表训练已充分，也不能作为算法优于其他方法的证据。

若暂时只查看运行过程，可以明确选择规则策略。

```bash
python -m ubisched serve --policy greedy_score --auto-schedule
```

另开终端，从同一项目根目录初始化示例任务。

```bash
python -m ubisched request --input configs/ubisched/v2_initialize.json
```

再分别启动三个离线示例执行端。

```bash
python -m ubisched worker --config configs/ubisched/worker_UAV1.mock.json
python -m ubisched worker --config configs/ubisched/worker_UAV2.mock.json
python -m ubisched worker --config configs/ubisched/worker_UAV3.mock.json
```

上面三个命令应在三个终端分别运行。配置里的程序都是 mock，不会启动 AirSim。
真实执行时，资源与执行程序的绑定方式见 `Docs/V2_RUNTIME_PROTOCOL.md`。

默认任务数据库是 `.ubisched/runtime.sqlite3`。相同任务重启服务时使用同一路径，可恢复指令和反馈记录。
开始另一项任务时，使用新的 `--database` 路径，并为执行端使用新的数据库路径。
运行中不要删除数据库。已有任务不允许再次 initialize 覆盖，只能用遥测、反馈和新增任务接口更新。

## 查看状态

```python
from ubisched.integration.client import RuntimeClient
client = RuntimeClient()
state = client.call("state")
print(state["summary"])
print(state["commands"])
```

默认只监听本机。多个客户端提交方案时，由同一协调器统一登记任务和资源占用。
这是一套单协调器的软件实现，不应写成已经完成分布式共识或实机系统验证。

## 单次推理和训练入口

```bash
python -m ubisched infer --snapshot configs/ubisched/structured_snapshot_example.json
python -m ubisched train --help
```

训练脚本支持 `mappo_mlp`、`mappo_transformer`、`mappo_dependency_transformer`、`mappo_critical_path_transformer`。
通过 `--models` 用逗号指定。默认仍为 MLP 和依赖增强 Transformer。
新训练权重保存输入约定及校验值，在线加载时进行严格核对。

训练与在线共用 `ubisched/config.py`。不要单独修改在线归一化参数。
修改任务特征、归一化方式、动作容量或单位后，应重新训练并使用新数据库。

## 新旧代码的位置

| 目录 | 用途 |
| --- | --- |
| `ubisched/` | 新版核心实现 |
| `scripts/demo_v2_runtime.py` | 新版离线完整演示 |
| `tests/test_v2_*.py` | 新版协议、恢复和模型接口测试 |
| `iSSROS/`、`plugins/` | 旧 C++ 运行方式及兼容接口 |
| `light_mappo-transformer/` | 原有算法工程，不是新版默认模型调用路径 |
| `Docs/` 中的阶段文档 | 历史说明，当前运行方式以本 README 和 V2 文档为准 |

旧 UBI1/UBI2/UBI2C 接口仍保留。UBI2 是无状态建议接口，新版有状态接口为本地 HTTP `/v2/rpc`。
UBI2C 只能返回旧传感器编号，不能用于完整的计算任务下发。
旧 C++ 请求失败时，默认停止本轮下发。只有显式设置 `UBISCHED_LEGACY_FALLBACK=1` 才启用旧算法回退。

## 阅读与当前边界

从 `Docs/V2_CODE_READING.md` 的第 1 步开始。在线运行、训练、可选算法、实验和兼容代码均已列入清单。

软件已补齐独立入口、统一配置、状态生产端接口、统一提交、持久化指令、执行反馈和超时处理。
仍待正式验证的部分是充分训练、多种子对比、消融和规模变化实验，以及 AirSim/真实执行程序接入后的联合验证。
任务耗时、通信和能耗仍使用估算模型。执行端的实际文件读取和数据传输由绑定程序完成，当前不宣称已经实测通信性能。
