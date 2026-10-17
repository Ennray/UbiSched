# 新版运行接口与执行端接入

## 1. 完整执行过程

启动 `python -m ubisched serve --auto-schedule` 后，服务等待初始化状态。
生产端 initialize 提交明确的任务图和资源图。自动调度循环读取当前状态并生成方案，随后在同一数据库事务里核验方案、占用资源和保存指令。
每个 UAV 的 worker 领取属于自己的指令，调用配置绑定的本机程序，并回报开始、完成或失败。
协调器根据反馈释放资源、解除后继任务的依赖，再安排下一轮任务。

没有执行反馈时，任务不会因为估计时间已到而被自动标记为完成。
服务端的图调度与旧 C++ 能力需求表没有调用依赖。

## 2. 请求格式

HTTP POST `/v2/rpc`，Content-Type 为 application/json。默认地址 `http://127.0.0.1:18767/v2/rpc`。
每个请求包含 `operation` 和唯一的 `request_id`。响应丢失时，应使用原请求及原编号重试。
相同编号配不同内容会被拒绝。请求去重结果保存到数据库，跨服务重启仍然有效。

| operation | 主要字段 | 行为 |
| --- | --- | --- |
| initialize | snapshot | 一次性初始化任务。禁止覆盖已存在任务 |
| state | 无 | 返回状态、全部指令及完成统计 |
| plan | expected_revision，可选 at | 根据当前图生成方案，不登记占用 |
| commit | expected_revision、plan_id，可选 at | 全部方案通过核验后一起提交，失败时全部回滚 |
| schedule | 可选 at | 服务内部一次检查超时、规划及提交。也可用于手动调度 |
| poll_commands | uav_id、worker_id，可选 at | 领取本 UAV 的指令，相同指令重发仍保留原 command_id |
| feedback | command_id、uav_id、worker_id、result，可选 at、event_time、outputs、execution_energy_used、detail | 接受执行反馈 |
| telemetry | expected_revision、resources、links、assessments，可选 at | 更新观测，不允许释放正在由本系统执行的资源 |
| add_tasks | expected_revision、tasks，可选 at | 在容量范围内添加带依赖的任务 |
| add_resources | expected_revision、resources，可选 at | 在容量范围内添加资源和 UAV |
| retry_task | expected_revision、subtask_id，可选 at | 确认失败或取消后，将任务重新排队 |
| cancel | expected_revision、command_id，可选 at | 请求停止任务，等待执行端确认 |
| sweep | 可选 at | 超时指令转入 cancelling，仍然保留资源占用 |

客户端代码 `RuntimeClient.call()` 会在网络故障时使用同一个请求编号重试。
`expected_revision` 从最新 state 或 plan 响应取得。任务、占用、反馈、遥测等状态发生变化后，旧方案将被拒绝。
时间推进本身不保证方案仍然有效，因此 commit 还会使用提交时刻的数据重新检查每项分配。

## 3. 时间、单位和输入约定

时间为任务开始后的秒数。deadline 和 arrival_time 都是任务开始后的绝对时刻。
如果不传 at，服务根据保存时的任务时间和实际经过时间推进任务时钟。若传 at，不能倒退。
event_time 用于延迟到达的执行反馈，可以早于当前任务时钟，但不得早于该指令已接收的上一条反馈。

数据量为 MB，频率为 GHz，计算量为 Gcycle，功率为 W，能量为 J，位置为米。
例如 10 Gcycle 在 2 GHz 节点上的理想计算时间是 5 秒。这里的 CPU 性能属于简化模型。

最大任务数为 8，最大 UAV 数为 3，每架 UAV 最多 3 个可执行资源。
一个子任务同时只分配一个资源。资源可以是传感器或计算节点。
通信使用 UAV 间有向直连路径，每条路径采用独占时间预约，不包含多跳和共享无线电竞争。

energy_normalization 保存任务初始能量归一化尺度，后续状态中保持不变，避免在线每轮按剩余电量重新缩放。
独立外部生产端在恢复中途状态时，也应提供相同的 energy_normalization。
运行中的任务必须提供 running_assignments。已经完成且向后继提供数据的任务必须提供 completed_assignments，明确数据来源资源。

## 4. 生产端示例

```python
from ubisched.integration.client import RuntimeClient
from ubisched.integration.telemetry import TelemetryProducer

client = RuntimeClient()
producer = TelemetryProducer(client)
state = client.call("state")
producer.publish(
    request_id="observation-0001",
    expected_revision=state["revision"],
    at=2.0,
    resources=[{"resource_id": "cam_0", "remaining_energy": 295.0}],
    assessments=[{"resource_id": "cam_0", "modality": "rgb",
                  "metric": "recognition", "scores": [80.0, 75.0, 60.0], "scale": 100.0}],
)
```

上述值仅演示格式。真实生产端应传实际采集或评估得到的值，并使用与当前任务一致的时间。
旧评估函数的三个返回值依次是探测、识别、测距。转换函数要求明确选择 metric，不自动猜测采用哪一项。
资源质量会进入新版匹配和策略观测，旧能力表不再是新版的必经步骤。

任务图必须由已知任务定义和执行反馈建立，不能从旧 obs0 数字串推断完整 DAG。
外部工作负载可以通过 telemetry 更新 occupied/release_time，但不能覆盖本系统 active 指令管理的占用。

## 5. 执行程序约定

worker 配置将每个 resource_id 绑定到 argv 列表。程序使用 shell=False 启动，网络指令不能指定要执行的程序。
同一 UAV 的不同资源可并行执行。程序在标准输入中收到一条 JSON 指令，包含 command_id、任务、资源编号及 inputs。
inputs 描述前驱任务、数据量及前驱 outputs。outputs 是文件路径或 URI 元数据，不会把图像字节塞进调度接口。

程序结束时，在标准输出写一份 JSON。

```json
{"result":"completed","outputs":{"image":"file:///data/capture.png"},"execution_energy_used":1.2}
```

result 可以是 completed、failed、cancelled。进程非零退出、无效 JSON 或本机执行超时会产生失败反馈。
execution_energy_used 可省略。它只表示执行资源的实测能耗，不包含发送节点的通信能耗。
没有实测值时，系统保留估算值，并在指令记录中明确 energy_kind。
真实执行程序负责图像采集、实际数据传送和推理。本版本未附带已验证的 AirSim 接收程序。

## 6. 超时、故障和恢复

服务超时后进入 cancelling，不立即释放资源。worker 在领取取消指令时，只有确认该任务未启动或已经停止，才能反馈 cancelled。
当前通用子进程 worker 通过本机执行超时终止程序。正在执行时不能立即接收服务端取消，取消响应最长受本机执行超时限制。
POSIX 平台会终止整个子进程组。Windows 只能保证直接子进程被终止，实际控制程序应管理其派生进程和设备停止过程。

worker 数据库在启动程序前写入指令编号。正常重发不会重复执行同一编号。
如果 worker 在执行中异常退出，且没有可靠结果，重启后返回 recovery_required，禁止自动重跑。
此时需要核对实际程序和设备是否已经停止，再使用 feedback 确认 completed、failed 或 cancelled。
确认失败后，如需重试，再调用 retry_task。不能靠删数据库强制重跑。

同一指令不会自动换绑另一个 worker_id。这是为了避免原执行端仍在运行时，由另一执行端重复启动。
恢复时保持原 worker_id 和数据库路径。需要更换执行端时，先确认旧端停止并完成反馈，再开始新的任务或重试。

协调器数据库保存任务状态、方案、指令和请求去重记录。worker 数据库保存实际启动记录与待回报结果。
服务和 worker 的数据库都应放在持久磁盘上。复制数据库用于迁移时，先正常停止进程，并同时处理 SQLite WAL 文件。
当前实现不包含认证服务、高可用和跨协调器一致性。默认本机使用；跨主机部署需要由外部认证网关和访问控制保护。
