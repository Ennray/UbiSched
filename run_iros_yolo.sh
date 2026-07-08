#!/usr/bin/env bash
set -euo pipefail

echo "=== Starting iS2ROS Modules ==="

declare -a PIDS=()

# ---------------------------------------------------------
# Task 1: Start IROS (pymerge-test env)
# ---------------------------------------------------------
echo "[1/2] Starting IROS (Port 8888, Node 1)..."
# 使用子 Shell 启动：激活环境 -> 运行 -> 退出子 Shell (环境自动隔离)
( source /venvs/pymerge-test/bin/activate && ./IROS 8888 1 </dev/null ) &
PIDS+=("$!")

# ---------------------------------------------------------
# Task 2: Start YOLOv5 Inference (pymerge-test env)
# ---------------------------------------------------------
echo "[2/2] Starting YOLOv5 Inference..."
VISION_SCRIPT="/home/jupyterWorkspace/is2ros_yolov5_inference_zc/yolov5_scripts/python_scripts/IR_test.py"

# 同样使用子 Shell，确保在 pymerge-test 环境下运行 IR_test.py
( source /venvs/pymerge-test/bin/activate && python -u $VISION_SCRIPT </dev/null ) &
PIDS+=("$!")

# ---------------------------------------------------------
# Cleanup & Wait
# ---------------------------------------------------------
echo "=== Initialization Complete ==="
echo "IROS PID: ${PIDS[0]} | YOLO PID: ${PIDS[1]}"
echo "?? Logs are printing directly to this terminal."
echo "Press Ctrl+C to stop all processes..."

# Trap Ctrl+C (SIGINT) to kill child processes cleanly
trap 'echo -e "\nStopping services..."; kill ${PIDS[*]} 2>/dev/null; exit 0' SIGINT SIGTERM

# Block and wait for background processes
wait
