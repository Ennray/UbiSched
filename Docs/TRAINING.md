# 当前训练与评估

## 入口与模型

唯一入口是 `python -m ubisched train`，实现在 `ubisched/training.py`。
它统一生成场景、运行三个规则基线、训练所选模型、独立评估并保存结果。

| `--models` 中的名称 | 作用 |
| --- | --- |
| `mappo_mlp` | 扁平输入的 MAPPO 基线 |
| `mappo_transformer` | 任务和资源联合注意力编码 |
| `mappo_dependency_transformer` | 加入任务依赖特征与两次后继信息聚合 |
| `mappo_critical_path_transformer` | 进一步加入近似关键路径时间预算 |

默认比较 MLP 和依赖增强模型。多个模型用逗号连接。
规则基线是随机可行、匹配评分贪心和最早截止时间，脚本自动运行。

## 第一步，检查训练流程

```bash
python -m ubisched train --models mappo_dependency_transformer --train-episodes 40 --train-seeds 11 --eval-cases 2 --batch-size 4 --ppo-epochs 2 --hidden 32 --heads 4 --layers 1 --output-dir outputs/train_check_01
```

一局包含一个任务集合从初始化到结束的完整调度过程。`batch-size` 是每次更新前收集的完整回合数。
`eval-cases` 是每种测试场景的案例数，不是全部场景合计。

## 第二步，初步对比

```bash
python -m ubisched train --models mappo_mlp,mappo_transformer,mappo_dependency_transformer --train-episodes 500 --train-seeds 11,29,47 --eval-cases 20 --batch-size 8 --ppo-epochs 4 --hidden 32 --heads 4 --layers 1 --output-dir outputs/experiment_01
```

这是第一轮配置，不保证收敛。根据训练趋势与独立验证结果决定是否增加回合数。
调参应使用独立验证集，最终测试集不用于反复挑选参数或随机种子。
需要比较关键路径模型时，将其加入 `--models`，使用相同训练预算和测试案例。

## 场景与数据

场景由 `ubisched/experiments/integrated_scenario.py` 生成，不需要 AirSim 或图像数据集。
默认 3 架 UAV、3 组采集与处理任务、6 个资源。
场景包含较快通信、较慢通信、路径中断和受限资源下的通信争用。
争用场景额外禁用部分计算资源，不能描述成只改变带宽。

训练与测试场景种子分离。同一训练种子下，各模型使用相同训练场景顺序。
这些是合成仿真数据，不是实测值，也不是公开权威数据集。

## 输出

| 文件 | 内容 |
| --- | --- |
| `experiment_config.json` | 模型、随机种子、场景和训练配置 |
| `training_log.csv` | 每批回合的奖励、完成率、损失和熵 |
| `evaluation_records.csv` | 各模型和规则的逐案例测试指标 |
| `comparison_summary.csv` | 按策略、场景、训练种子汇总 |
| `cross_seed_summary.csv` | 跨训练种子均值和标准差 |
| `progress.json` | 已完成的模型及种子、全部是否结束 |
| `<model>_seed_<seed>.pt` | 模型参数、结构配置和输入约定 |

关注按时完成率、整体完成时间、能耗、超期和通信排队。完成率相同不代表性能相同。

## 当前限制

- CPU 单线程执行，没有 GPU 选择参数。
- 每个模型和种子训练结束后才保存权重，完成评估后才更新 CSV 并打印进度。
- 没有中途检查点和断点续训。中断的模型需要重新训练。
- 重用输出目录会覆盖同名结果，每项实验应使用新的目录。
- `hidden` 必须能被 `heads` 整除，所有数值参数必须为正数。
- 容量上限为 8 个任务、3 架 UAV、每架最多 3 个资源。当前默认训练场景小于部分上限，不代表已经证明规模泛化。

## 训练与在线一致性

特征、容量、单位、归一化、评分和奖励约定继续由 `ubisched/config.py` 管理。
本次清理没有改变这些约定，也没有修改四种模型的参数更新算法。
修改上述约定后，应重新训练。加载时会检查权重中的输入约定和校验值。
包内两份 `smoke_*.pt` 为原有 24 回合检查权重，仅修改文件名，字节内容不变。
