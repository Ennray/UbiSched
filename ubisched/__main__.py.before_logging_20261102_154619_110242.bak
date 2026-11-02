"""新版唯一命令入口。python -m ubisched --help"""
import argparse
import json
import sys
from pathlib import Path


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "train":
        from scripts.run_stage11_integrated import main as train_main
        return train_main(argv[1:])
    parser = argparse.ArgumentParser(description="UbiSched 新版图调度")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="启动带持久化状态的新版服务")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=18767)
    serve.add_argument("--database", type=Path, default=Path(".ubisched/runtime.sqlite3"))
    serve.add_argument("--policy", default="mappo_dependency_transformer",
                       choices=("greedy_score", "earliest_deadline", "mappo_mlp", "mappo_transformer",
                                "mappo_dependency_transformer", "mappo_critical_path_transformer"))
    serve.add_argument("--checkpoint", type=Path)
    serve.add_argument("--auto-schedule", action="store_true", help="初始化后自动规划、提交，并检查超时")
    serve.add_argument("--command-timeout", type=float, default=30)
    rpc = commands.add_parser("request", help="发送初始化、规划、提交、遥测或反馈请求")
    rpc.add_argument("--input", required=True, type=Path, help="包含 operation/request_id 的 JSON 文件")
    rpc.add_argument("--url", default="http://127.0.0.1:18767/v2/rpc")
    infer = commands.add_parser("infer", help="单次离线推理，只返回建议")
    infer.add_argument("--snapshot", type=Path, required=True)
    infer.add_argument("--policy", default="greedy_score")
    infer.add_argument("--checkpoint", type=Path)
    worker = commands.add_parser("worker", help="执行指定资源的本机程序并回报结果")
    worker.add_argument("--config", type=Path, required=True)
    worker.add_argument("--once", action="store_true")
    train = commands.add_parser("train", help="训练/正式实验入口，参数由训练脚本解释")
    train.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command == "serve":
        from ubisched.integration.structured_bridge import ModelPolicy
        from ubisched.integration.runtime import RuntimeCoordinator
        from ubisched.integration.runtime_server import RuntimeServer
        if not 1 <= args.port <= 65535:
            parser.error("port must be within 1..65535")
        checkpoint = args.checkpoint
        if checkpoint is None and args.policy == "mappo_dependency_transformer":
            checkpoint = Path(__file__).resolve().parents[1] / "models/stage11_dependency_transformer_seed11.pt"
        coordinator = RuntimeCoordinator(ModelPolicy(args.policy, checkpoint), args.database,
                                         command_timeout=args.command_timeout)
        try:
            with RuntimeServer((args.host, args.port), coordinator) as server:
                from ubisched.integration.scheduler import SchedulerLoop
                loop = SchedulerLoop(coordinator) if args.auto_schedule else None
                if loop:
                    loop.start()
                print(f"UbiSched v2 ready http://{args.host}:{args.port}/v2/rpc policy={args.policy}", flush=True)
                try:
                    server.serve_forever(poll_interval=0.1)
                except KeyboardInterrupt:
                    pass
                finally:
                    if loop:
                        loop.stop()
        finally:
            coordinator.close()
        return 0
    if args.command == "request":
        from ubisched.integration.client import RuntimeClient
        request = json.loads(args.input.read_text(encoding="utf-8"))
        operation = request.pop("operation")
        result = RuntimeClient(args.url).call(operation, **request)
    elif args.command == "infer":
        from ubisched.integration.structured_bridge import ModelPolicy, StructuredAdapter
        result = StructuredAdapter(ModelPolicy(args.policy, args.checkpoint)).decide(
            json.loads(args.snapshot.read_text(encoding="utf-8")))
    elif args.command == "worker":
        from ubisched.integration.worker import ExecutionWorker
        worker = ExecutionWorker.from_file(args.config)
        try:
            if args.once:
                result = worker.run_once()
            else:
                worker.run_forever(); return 0
        finally:
            worker.close()
    else:
        from scripts.run_stage11_integrated import main as train_main
        return train_main(args.args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
