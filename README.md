# UbiSched 精简版

本分支基于 UbiSched v2.1，只保留新版任务图调度、训练评估、HTTP 服务和执行反馈。
分支名为 `cleanup/new-runtime`，原始快照保存在 `archive/v2.1-original`。

## 目录

| 路径 | 职责 |
| --- | --- |
| `ubisched/__main__.py` | 唯一命令入口 |
| `ubisched/config.py` | 容量、单位、评分和模型输入约定 |
| `ubisched/graph/` | 任务图、资源图、匹配、依赖和通信代价 |
| `ubisched/scheduling/` | 调度状态、资源占用、仿真环境和动作约束 |
| `ubisched/algorithms/` | 四种 MAPPO 模型 |
| `ubisched/integration/policy.py` | 模型加载和结构化分配建议 |
| `ubisched/integration/` 其他文件 | HTTP 服务、数据库、状态生产端和执行端 |
| `ubisched/training.py` | 统一训练与评估 |
| `configs/ubisched/` | 当前运行示例与组件测试配置 |
| `models/` | 两份只用于检查接口的短训练权重 |
| `scripts/` | 一个完整演示及其模拟执行程序 |
| `tests/` | 当前组件与端到端回归；`support/` 只供测试使用 |
| `Docs/` | 当前协议、训练说明、阅读顺序和清理记录 |

## 安装

使用独立的 Python 3.10 及以上环境。以下命令均在项目根目录执行。

```bash
python -m pip install -e ".[models,dev]"
python -m ubisched --help
```

只运行规则策略和模拟执行，可以用 `python -m pip install -e .`，无需 PyTorch。
训练和学习策略需要 `models` 依赖；回归测试需要 `dev` 依赖。

## 一条命令检查完整流程

```bash
python scripts/demo_v2_runtime.py
```

正常结果为 6 个任务完成、0 个失败、6 条指令，`all_finished` 为 `true`。
演示使用临时数据库和模拟执行，不控制 AirSim，不采集图像，也不运行识别模型。

## 分进程运行

第一个终端启动服务，首次查看过程可明确选择规则策略。

```bash
python -m ubisched serve --policy greedy_score --auto-schedule --command-timeout 300
```

第二个终端提交示例任务和资源。

```bash
python -m ubisched request --input configs/ubisched/v2_initialize.json
```

随后在三个终端分别运行以下命令，所有终端均使用同一 Python 环境和项目根目录。

```bash
python -m ubisched worker --config configs/ubisched/worker_UAV1.mock.json
python -m ubisched worker --config configs/ubisched/worker_UAV2.mock.json
python -m ubisched worker --config configs/ubisched/worker_UAV3.mock.json
```

三个命令分别常驻，不能在同一终端逐条等待完成。初始化后及时启动执行端。
配置绑定的程序为 `scripts/mock_executor.py`。

查看状态。

```bash
python -c "from ubisched.integration.client import RuntimeClient; print(RuntimeClient().call('state')['summary'])"
```

默认服务地址为 `http://127.0.0.1:18767/v2/rpc`，数据库为 `.ubisched/runtime.sqlite3`。
同一次任务恢复时保留服务和 worker 数据库、worker_id。开始新任务时，为服务和三个 worker 分别指定新的数据库路径。
运行中不要删数据库，已有任务不能再次初始化覆盖。服务和 worker 用 Ctrl+C 正常停止。

## 训练与模型运行

统一入口如下。此命令只检查训练、保存与加载，不用于证明算法效果。

```bash
python -m ubisched train --models mappo_dependency_transformer --train-episodes 40 --train-seeds 11 --eval-cases 2 --output-dir outputs/train_check_01
```

加载刚训练的权重做单次推理。

```bash
python -m ubisched infer --snapshot configs/ubisched/structured_snapshot_example.json --policy mappo_dependency_transformer --checkpoint outputs/train_check_01/mappo_dependency_transformer_seed_11.pt
```

加载同一权重运行服务。

```bash
python -m ubisched serve --policy mappo_dependency_transformer --checkpoint outputs/train_check_01/mappo_dependency_transformer_seed_11.pt --auto-schedule
```

`serve --auto-schedule` 未指定策略时仍使用依赖增强模型和包内检查权重。
`models/smoke_*.pt` 只训练过 24 回合，不能作为正式实验结论。四种模型均保留，详见 [训练说明](Docs/TRAINING.md)。

## 阅读与验证

```bash
python -m pytest tests -q
```

- [代码阅读顺序](Docs/CODE_READING.md)
- [运行与执行端协议](Docs/RUNTIME_PROTOCOL.md)
- [训练说明](Docs/TRAINING.md)
- [清理范围与 Git 分支使用](Docs/CLEANUP.md)
- [本次验证](Docs/VALIDATION.md)

任务耗时、能耗和通信仍为估算模型。真实采集、识别和数据传送需要绑定实际执行程序，后续再与 AirSim 联合验证。
