"""Launch the current graph policy using the old iS2ROS socket formats."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ubisched.integration.legacy_network import main

if __name__ == "__main__":
    raise SystemExit(main())
