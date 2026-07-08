#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PORTS=(8888 8889 8890 8891 8892)

echo "Stopping IROS instances on ports: ${PORTS[*]}"

# 1. 尝试温和地杀死 IROS 实例
for port in "${PORTS[@]}"; do
    pids=()
    # 使用 for 循环直接遍历 pgrep 的输出，完全避免进程替换
    for pid in $(pgrep -f "IROS ${port} " 2>/dev/null || true); do
        pids+=("$pid")
    done

    if [[ ${#pids[@]} -gt 0 ]]; then
        echo "Killing IROS on port ${port}: ${pids[*]}"
        kill "${pids[@]}" 2>/dev/null || true
    fi
done

# 2. 杀死启动脚本 (通用写法，只匹配文件名)
pids=()
for pid in $(pgrep -f "run_5_iros.sh" 2>/dev/null || true); do
    pids+=("$pid")
done

if [[ ${#pids[@]} -gt 0 ]]; then
    echo "Killing launcher shells: ${pids[*]}"
    kill "${pids[@]}" 2>/dev/null || true
fi

# 3. 强制杀死残留进程
for port in "${PORTS[@]}"; do
    pids=()
    for pid in $(pgrep -f "IROS ${port} " 2>/dev/null || true); do
        pids+=("$pid")
    done

    if [[ ${#pids[@]} -gt 0 ]]; then
        echo "Force killing remaining on port ${port}: ${pids[*]}"
        kill -9 "${pids[@]}" 2>/dev/null || true
    fi
done

# 4. 检查端口占用
if command -v ss >/dev/null 2>&1; then
    echo "Remaining UDP listeners on 8888-8892:"
    ss -lunp 2>/dev/null | grep -E ':(8888|8889|8890|8891|8892)\b' || echo "none"
fi

echo "Done."