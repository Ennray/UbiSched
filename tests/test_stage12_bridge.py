import json
import socket
import threading

import pytest

from ubisched.integration.is2ros_bridge import (
    BridgeServer, LegacyUbiSchedAdapter, ProtocolError, default_profile,
)


def test_protocol_rejects_bad_packets():
    adapter = LegacyUbiSchedAdapter()
    for raw in (b"UBI9|1|101", b"UBI1|0|101", b"UBI1|1|abc",
                b"UBI1|1|1", b"UBI1|1|1" + b"1" * 200,
                b"UBI1|1|111|extra", b"\xff"):
        assert adapter.handle(raw).startswith(b"ERR|")


def test_valid_response_has_legacy_action_index_and_sensor():
    adapter = LegacyUbiSchedAdapter()
    data = adapter.handle(b"UBI1|3|1101")
    assert data.startswith(b"OK|")
    _, task, sensor = data.decode().split("|")
    assert int(task) in (0, 2)
    assert int(sensor) in (0, 1, 2)


def test_no_tasks_has_no_allocation():
    assert LegacyUbiSchedAdapter().handle(b"UBI1|2|1000") == b"NONE"


def test_task_modality_changes_sensor_choice():
    profile = default_profile()
    profile["sensors"][1]["modality"] = "infrared"
    profile["modality_by_task"] = {"0": "infrared"}
    assert LegacyUbiSchedAdapter(profile).handle(b"UBI1|1|1100") == b"OK|0|1"


def test_offline_resource_never_selected():
    profile = default_profile()
    for s in profile["sensors"]:
        s["online"] = False
    assert LegacyUbiSchedAdapter(profile).handle(b"UBI1|1|11") == b"NONE"


def test_unconfigured_modality_returns_none():
    profile = default_profile()
    profile["modality_by_task"] = {"0": "radar"}
    assert LegacyUbiSchedAdapter(profile).handle(b"UBI1|1|11") == b"NONE"


def test_duplicate_or_invalid_sensor_rejected():
    profile = default_profile()
    profile["sensors"][2]["legacy_sensor_index"] = 1
    with pytest.raises(ProtocolError):
        LegacyUbiSchedAdapter(profile)


def test_snapshot_is_rechecked_each_request():
    adapter = LegacyUbiSchedAdapter()
    assert adapter.handle(b"UBI1|1|110") == b"OK|0|0"
    assert adapter.handle(b"UBI1|1|101") == b"OK|1|0"


def test_loopback_udp_round_trip():
    adapter = LegacyUbiSchedAdapter()
    with BridgeServer(("127.0.0.1", 0), adapter) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(1)
                sock.sendto(b"UBI1|1|110", server.server_address)
                data, _ = sock.recvfrom(128)
            assert data == b"OK|0|0"
        finally:
            server.shutdown()
            thread.join(timeout=2)
