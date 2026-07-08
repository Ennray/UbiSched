#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$ROOT_DIR"
LOG_DIR="$BUILD_DIR/logs"
mkdir -p "$LOG_DIR"

if [[ ! -x "$BUILD_DIR/IROS" ]]; then
  echo "IROS not found, building first..."
  mkdir -p "$BUILD_DIR"
  cmake -S "$ROOT_DIR" -B "$BUILD_DIR"
  cmake --build "$BUILD_DIR" -j8
fi

# 可选：覆盖回传到Windows的目标IP
# export IROS_DISPATCH_IP=172.26.160.1

declare -a PIDS=()
for i in 1 2 3 4 5; do
  port=$((8887 + i))
  log_file="$LOG_DIR/iros_uav${i}.log"
  echo "Starting UAV${i}: port=${port}, log=${log_file}"
  (cd "$BUILD_DIR" && ./IROS "$port" "$i" >"$log_file" 2>&1) &
  PIDS+=("$!")
done

echo "Started 5 IROS instances."
echo "PIDs: ${PIDS[*]}"
echo "Stop all with: kill ${PIDS[*]}"
