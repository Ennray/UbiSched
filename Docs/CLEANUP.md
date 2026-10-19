# 精简范围与分支使用

本次以用户提供的 `UbiSched_v2.1.zip` 为原始快照。
压缩包不含 `.git`，因此先新建快照仓库，再在独立分支清理。
这里的 Git 历史从该快照开始，不是原项目之前的完整开发历史。

| 分支 | 内容 |
| --- | --- |
| `archive/v2.1-original` | 原始快照的基线提交 |
| `cleanup/new-runtime` | 精简后的新版主流程与回归测试 |

## 移除内容

- `iSSROS/`、`plugins/` 及相关 CMake、Makefile、交叉编译和启动脚本。
- `light_mappo-transformer/` 旧算法工程、旧权重和旧训练输出。
- `Baks/`、`文档/`、零散文本、旧架构图片、空文档和重复阶段说明。
- `outputs/stage4_experiment/` 历史实验记录，原始值仍在基线分支。
- UBI1、UBI2、UBI2C 的 UDP 兼容实现及其 C++ 探针和专用测试。
- 早期独立规则调度器，当前规则策略继续使用统一环境中的贪心和 EDF 实现。
- 重复的阶段演示、训练、诊断及快照转换脚本。
- 仅测试上述旧入口的用例。算法、约束、状态、反馈和当前入口的测试继续保留。

## 保留内容

- 任务图、资源图、匹配、动作掩码、任务依赖和关键路径。
- 执行与通信估算、资源占用、时间预约、能量检查和动态更新。
- 四种 MAPPO 模型、规则基线和统一训练评估入口。
- HTTP 服务、客户端、生产端接口、worker、数据库恢复、去重、取消及超时。
- 两份原有短训练检查权重，文件名改为 `smoke_*.pt`，内容不变。
- 环境质量评估结果转换接口，后续可用于接入外部评估程序。
- 没有数据依赖边时，依据任务输入数据量估算传输的分支。它仍被组件使用，不是无用代码。

模型特征顺序、容量、单位、评分、奖励、PPO 和注意力计算保持原约定。
本次是源码整理，不新增断点训练、GPU、AirSim 程序或算法效果结论。

## 代码包与 Git 包

源码 zip 只含精简后的文件，不含 `.git`。解压后可直接按 README 运行。
Git bundle 包含原始快照及精简分支历史，需要保留真实分支时使用它。

在 bundle 所在目录执行。

```bash
git clone -b cleanup/new-runtime UbiSched_cleanup_branches.bundle UbiSched-clean
cd UbiSched-clean
git branch -a
```

克隆后的当前分支是 `cleanup/new-runtime`，可以直接继续修改和提交。
bundle 克隆的 origin 指向本地文件，后续有自己的远程仓库时再调整 origin。

查看清理差异。

```bash
git diff --stat origin/archive/v2.1-original..cleanup/new-runtime
```

如需单独查看原版，先保存自己的工作，再切换到原始快照。

```bash
git switch -c archive/v2.1-original origin/archive/v2.1-original
```

不建议把精简包直接覆盖到旧目录。覆盖解压不会自动删除旧文件，容易再次混入历史内容。
使用新的目录，或通过 bundle 切换分支。

## 详细记录

`CLEANUP_MANIFEST.json` 记录原始基线、文件移动、删除清单与整理后规模。
`VALIDATION.md` 记录本次实际执行的检查，历史验证报告已从精简分支移除。
