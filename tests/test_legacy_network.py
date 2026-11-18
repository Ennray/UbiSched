"""Compatibility tests use actual localhost sockets and the current graph adapter."""
import socket
import threading
import time

import pytest

from ubisched.integration.legacy_network import (
    LegacyGraphPolicy, TcpSession, correlation_key, default_profile,
    extract_udp_observation, parse_observation, recv_exact, run_tcp, run_udp)
from ubisched.integration.structured_bridge import ModelPolicy


def policy():
    return LegacyGraphPolicy(ModelPolicy("greedy_score"), default_profile())


def port():
    with socket.socket() as s:
        s.bind(("127.0.0.1",0))
        return s.getsockname()[1]


def test_graph_policy_only_selects_available_unique_tasks_and_configured_sensors():
    result = policy().decide("011110", ["UAV1","UAV2"])
    assert len(result)==2
    assert len({c["task_index"] for c in result})==2
    assert all(c["task_index"] in {0,1,2,3} and c["sensor_index"] in {0,1} for c in result)
    assert {c["uav_id"] for c in result}=={"UAV1","UAV2"}


def test_two_round_tcp_masks_and_replays_and_final_report():
    session=TcpSession(policy(),["UAV1","UAV2"])
    obs="011110"
    for _ in range(2):
        reply=session.reply(obs)
        assert len(reply)==4 and reply.isdigit()
        assert session.reply(obs)==reply
        chars=list(obs)
        for c in session.previous[2]:
            chars[c["task_index"]+1]="0"
        chars[0]=str(3-int(chars[0]))
        obs="".join(chars)
    assert session.reply(obs) is None


def test_odd_batch_or_ambiguous_marker_never_duplicates_a_task():
    session=TcpSession(policy(),["UAV1","UAV2"])
    with pytest.raises(ValueError,match="idle UAV"):
        session.reply("010000")
    session.reply("011110")
    with pytest.raises(ValueError,match="marker"):
        session.reply("010110")


@pytest.mark.parametrize("data",[b"11111",b"011112",b"x11110",b"0111100",b"\xff11110"])
def test_invalid_old_observation_rejected(data):
    with pytest.raises((ValueError,UnicodeError)):
        parse_observation(data,5)


def test_weather_only_does_not_reuse_stale_task_state():
    with pytest.raises(ValueError,match="no task state"):
        extract_udp_observation(b"12:00#1#0#0#0",5)
    obs,weather=extract_udp_observation(b"12:00#1#0.1#0#0#011110",5)
    assert obs=="011110" and weather["fog"]=="0.1"


def test_tcp_real_socket_fragmentation_and_exact_reply_bytes():
    errors=[]; stop=threading.Event()
    with socket.socket() as server:
        server.bind(("127.0.0.1",0));server.listen(1);server.settimeout(3)
        def board():
            try:run_tcp(policy(),"127.0.0.1",server.getsockname()[1],["UAV1","UAV2"],stop)
            except Exception as exc:errors.append(exc)
        thread=threading.Thread(target=board);thread.start()
        conn,_=server.accept()
        with conn:
            conn.settimeout(2)
            obs="011110"
            for _ in range(2):
                conn.sendall(obs[:2].encode());time.sleep(.01);conn.sendall(obs[2:].encode())
                reply=recv_exact(conn,4,stop).decode()
                a,b,c,d=map(int,reply)
                assert a!=c and obs[a+1]==obs[c+1]=="1"
                chars=list(obs);chars[a+1]=chars[c+1]="0";chars[0]=str(3-int(chars[0]));obs="".join(chars)
            conn.sendall(obs.encode())
        thread.join(3);assert not thread.is_alive();assert not errors


@pytest.mark.parametrize("cpp",[False,True])
def test_udp_original_wire_formats_and_reply_ports(cpp):
    stop=threading.Event();listen_port=port();errors=[]
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as receiver:
        receiver.bind(("127.0.0.1",0));receiver.settimeout(.2)
        target_port=receiver.getsockname()[1]
        def board():
            try:run_udp(policy(),"127.0.0.1",listen_port,"127.0.0.1",target_port,"UAV1",stop,cpp)
            except Exception as exc:errors.append(exc)
        thread=threading.Thread(target=board);thread.start()
        data=b"UBI1|1|011110" if cpp else b"12:00#1#0#0#0#011110"
        try:
            for _ in range(15):
                receiver.sendto(data,("127.0.0.1",listen_port))
                try:reply,_=receiver.recvfrom(128);break
                except socket.timeout:continue
            else:raise AssertionError("no UDP reply")
            parts=reply.decode().split("|" if cpp else "#")
            if cpp:
                assert parts[0]=="OK" and int(parts[1]) in range(4) and parts[2] in {"0","1"}
            else:
                assert int(parts[0]) in range(4) and parts[1] in {"0","1"} and parts[2]=="UAV1"
        finally:
            stop.set();thread.join(2)
        assert not thread.is_alive() and not errors


def test_correlation_is_stable_without_claiming_new_wire_command_id():
    assert correlation_key("tcp","011110","UAV1",0,1)==correlation_key("tcp","011110","UAV1",0,1)
    assert correlation_key("tcp","011110","UAV1",0,1)!=correlation_key("tcp","011110","UAV2",0,1)
