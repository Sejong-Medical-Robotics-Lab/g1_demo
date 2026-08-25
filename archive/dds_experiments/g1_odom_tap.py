#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_odom_tap.py — [3.11 전용] 로봇 내장 오도메트리 구독 → UDP 전달

이 파일은 반드시 venv311 에서 실행한다 (로봇을 들을 수 있는 유일한 환경).
받은 값을 127.0.0.1:17777 로 JSON 을 쏘고, 반대편의 g1_odom_relay.py
(일반 ROS 터미널)가 받아 /odom + TF 로 발행한다.

사용:
    source ~/venv311/bin/activate
    python3 ~/g1_real/g1_odom_tap.py --iface $G1_IFACE
"""
import argparse
import json
import math
import socket
import sys
import time

from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
from unitree_sdk2py.idl.unitree_go.msg.dds_ import SportModeState_

UDP_ADDR = ("127.0.0.1", 17777)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iface", required=True)
    ap.add_argument("--topic", default="rt/odommodestate",
                    help="probe 에서 다른 토픽이 정답으로 나오면 바꿔서 실행")
    args = ap.parse_args()
    if not args.iface.strip():
        sys.exit("\n  [중단] --iface 비어 있음 — export G1_IFACE=enx...\n")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    state = {"n": 0, "last_log": 0.0}

    def on_msg(m: SportModeState_):
        q = m.imu_state.quaternion          # [w,x,y,z]
        yaw = math.atan2(2.0 * (q[0] * q[3] + q[1] * q[2]),
                         1.0 - 2.0 * (q[2] * q[2] + q[3] * q[3]))
        pkt = json.dumps({
            "x": float(m.position[0]), "y": float(m.position[1]),
            "yaw": yaw,
            "vx": float(m.velocity[0]), "vy": float(m.velocity[1]),
            "wz": float(m.imu_state.gyroscope[2]),
        }).encode()
        sock.sendto(pkt, UDP_ADDR)
        state["n"] += 1
        now = time.monotonic()
        if now - state["last_log"] > 2.0:
            state["last_log"] = now
            print(f"  #{state['n']:6d}  pos=({m.position[0]:+.2f},{m.position[1]:+.2f})"
                  f"  yaw={math.degrees(yaw):+7.1f}도  → UDP:17777")

    ChannelFactoryInitialize(0, args.iface)
    sub = ChannelSubscriber(args.topic, SportModeState_)
    sub.Init(on_msg, 10)

    print(f"  [{args.topic}] 구독 → UDP 127.0.0.1:17777 전달 중 (Ctrl+C 종료)")
    print("  5초 넘게 첫 줄이 안 뜨면: 로봇 전원/토픽명 확인 (probe_odom311)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n  종료 — 총 {state['n']}건 전달")


if __name__ == "__main__":
    main()
