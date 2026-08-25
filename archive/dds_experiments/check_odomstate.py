#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_odomstate.py — G1 내장 오도메트리 확인 (폴링판, venv_dds 전용)

사용:
    source ~/g1_real/dds_env.sh
    python3 ~/g1_real/check_odomstate.py --iface $G1_IFACE

성공: position/yaw 가 흐르고, 로봇을 밀면 값이 따라 변함
"""
import argparse
import math
import signal
import sys
import time

from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
from unitree_sdk2py.idl.unitree_go.msg.dds_ import SportModeState_


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iface", required=True)
    args = ap.parse_args()
    if not args.iface.strip():
        sys.exit("\n  [중단] --iface 비어 있음 — export G1_IFACE=enx... 후 재실행\n")

    signal.signal(signal.SIGALRM,
                  lambda *a: sys.exit("\n  [실패] Read 무한대기 — 짝맺기 실패 정황"))
    signal.alarm(15)
    ChannelFactoryInitialize(0, args.iface)
    sub = ChannelSubscriber("rt/odommodestate", SportModeState_)
    sub.Init()                      # 폴링 모드

    print("  rt/odommodestate 10초 폴링... (로봇을 살짝 밀면 값이 변해야 정상)")
    t0 = time.time()
    count = 0
    last_print = 0.0
    while time.time() - t0 < 10:
        m = sub.Read(100)
        if m is None:
            continue
        count += 1
        now = time.monotonic()
        if now - last_print < 0.5:
            continue
        last_print = now
        q = m.imu_state.quaternion
        yaw = math.atan2(2.0 * (q[0] * q[3] + q[1] * q[2]),
                         1.0 - 2.0 * (q[2] * q[2] + q[3] * q[3]))
        print(f"  #{count:5d}  pos=({m.position[0]:+.3f}, {m.position[1]:+.3f})"
              f"  yaw={math.degrees(yaw):+7.2f}도"
              f"  v=({m.velocity[0]:+.2f}, {m.velocity[1]:+.2f})")

    if count == 0:
        print("\n  [실패] 10초 무수신 — 이 토픽/타입 조합이 아님. probe_odom 결과 공유")
        sys.exit(1)
    print(f"\n  [성공] 총 {count}건 (약 {count/10:.0f}Hz) — B안 진행!")


if __name__ == "__main__":
    main()
