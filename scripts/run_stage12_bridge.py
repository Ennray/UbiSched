"""Start iS2ROS legacy bridge from the UbiSched project root."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ubisched.integration.is2ros_bridge import main

if __name__ == "__main__":
    main()
