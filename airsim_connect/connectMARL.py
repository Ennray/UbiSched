"""AirSim controller using the unchanged old iS2ROS TCP messages."""
from pathlib import Path
from airsim_legacy_control import main

if __name__ == "__main__":
    raise SystemExit(main(Path(__file__).with_name("airsim_legacy_config.json")))
