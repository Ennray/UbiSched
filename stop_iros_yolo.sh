#!/usr/bin/env bash

echo "=== Stopping iS2ROS processes ==="

# 1. Kill all IROS instances (ignores ports/args)
if pgrep -f "IROS" > /dev/null; then
    echo "Stopping IROS..."
    pkill -f "IROS"
else
    echo "No IROS process found."
fi

# 2. Kill YOLO inference script
if pgrep -f "IR_test.py" > /dev/null; then
    echo "Stopping YOLO (IR_test.py)..."
    pkill -f "IR_test.py"
else
    echo "No YOLO process found."
fi

# 3. Kill background launcher script
if pgrep -f "run_iros_yolo.sh" > /dev/null; then
    echo "Cleaning up run_iros_yolo.sh..."
    pkill -f "run_iros_yolo.sh"
fi

echo "=== All services stopped! ==="
