from __future__ import annotations

"""Atomic handoff from an external state producer to the iS2ROS bridge.

Input JSON is a *fully observed* UBI2 snapshot; this utility never invents
runtime telemetry or interprets an old iS2ROS numeric observation as a DAG.
"""
import argparse
import json
import os
from pathlib import Path
import tempfile

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ubisched.integration.structured_bridge import make_live_env


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    snapshot = json.loads(args.input.read_text(encoding="utf-8"))
    make_live_env(snapshot)  # reject invalid/over-capacity snapshots before publication
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".ubi2_", suffix=".tmp", dir=args.output.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(snapshot, out, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, args.output)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    print(f"Published: {args.output}")


if __name__ == "__main__":
    main()
