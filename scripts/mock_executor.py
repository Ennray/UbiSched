"""离线协议演示程序。没有采集图像、执行识别或控制无人机。"""
import json
import sys

command = json.load(sys.stdin)
print(json.dumps({"result": "completed", "outputs": {
    "demo": f"mock://{command['command_id']}/{command['subtask_id']}"}}))
