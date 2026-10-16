from __future__ import annotations

"""Send a structured live-state snapshot to a running UBI2 service.

Offline interface check only: response is a proposal, NOT a UAV dispatch.
"""
import argparse
import json
from pathlib import Path
import socket


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, default=Path("configs/ubisched/structured_snapshot_example.json"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18766)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    wire = b"UBI2|" + json.dumps(snapshot, ensure_ascii=False).encode("utf-8")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(3)
        sock.sendto(wire, (args.host, args.port))
        response, _ = sock.recvfrom(64000)
    print(response.decode("utf-8"))


if __name__ == "__main__":
    main()
