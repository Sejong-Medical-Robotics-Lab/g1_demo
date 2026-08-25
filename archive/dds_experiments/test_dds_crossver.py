#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_dds_crossver.py — 세대 간 통신 판정 (구세대 발행 → 신세대 구독)

상황: venv_dds(11.x)에서 루프백은 되는데 로봇 토픽은 전부 무수신.
가설: 11.x 구독자가 0.10대 발행자(=로봇 펌웨어 세대)와 짝을 못 맺는다.

이 스크립트는 **기존 venv 의 파이썬**으로 발행자를 띄우고(0.10대,
발행 경로는 멀쩡함이 검증됨), **현재 venv_dds** 로 구독한다:

    [수신 OK] → 세대 간 통신 정상 → 로봇이 그 토픽들을 진짜 안 쏘는 것
                → 다음: 실제 토픽명 조회(2차 수단)
    [무수신]  → 세대 간 짝맺기 실패 확정 → 11.x 로는 로봇 못 듣는다
                → 다음: Python 3.11 릴레이 (최종 정공법)

사용 (venv_dds 에서):
    source ~/g1_real/dds_env.sh
    python3 ~/g1_real/test_dds_crossver.py --iface $G1_IFACE
"""
import argparse
import os
import subprocess
import sys
import textwrap
import time

OLD_PY = os.path.expanduser("~/unitree_sdk2_python/.venv/bin/python3")

PUB = textwrap.dedent("""
    import time
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelPublisher
    from unitree_sdk2py.idl.unitree_go.msg.dds_ import SportModeState_
    from unitree_sdk2py.idl.default import unitree_go_msg_dds__SportModeState_

    ChannelFactoryInitialize(0, "{iface}")
    pub = ChannelPublisher("rt/crossver_test", SportModeState_)
    pub.Init()
    msg = unitree_go_msg_dds__SportModeState_()
    msg.position[0] = 7.77
    msg.position[1] = 8.88
    for _ in range(80):
        pub.Write(msg)
        time.sleep(0.1)
""")

SUB = textwrap.dedent("""
    import sys, time, signal
    signal.signal(signal.SIGALRM, lambda *a: sys.exit(42))
    signal.alarm(8)
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
    from unitree_sdk2py.idl.unitree_go.msg.dds_ import SportModeState_

    ChannelFactoryInitialize(0, "{iface}")
    sub = ChannelSubscriber("rt/crossver_test", SportModeState_)
    sub.Init()
    t0 = time.time()
    while time.time() - t0 < 6:
        m = sub.Read(200)
        if m is not None:
            print(f"HIT pos=({{m.position[0]:.2f}},{{m.position[1]:.2f}})")
            sys.exit(0)
    sys.exit(42)
""")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iface", required=True)
    args = ap.parse_args()
    if not args.iface.strip():
        sys.exit("\n  [중단] --iface 비어 있음\n")
    if not os.path.exists(OLD_PY):
        sys.exit(f"\n  [중단] 기존 venv 파이썬을 못 찾음: {OLD_PY}\n")

    print("  구세대(기존 venv, 0.10대) 발행 → 신세대(venv_dds, 11.x) 구독\n")
    pub = subprocess.Popen([OLD_PY, "-c", PUB.format(iface=args.iface)],
                           stderr=subprocess.PIPE, text=True)
    time.sleep(1.5)
    try:
        sub = subprocess.run([sys.executable, "-c", SUB.format(iface=args.iface)],
                             capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        pub.terminate()
        print("  [무수신]   (Read 무한대기 — 세대 간 짝맺기 실패 정황)")
        print("\n  → Python 3.11 릴레이로 확정 전환")
        return
    pub.terminate()
    pub_err = (pub.stderr.read() or "").strip().splitlines()

    if sub.returncode == 0 and sub.stdout.startswith("HIT"):
        print(f"  [수신 OK]  {sub.stdout.strip()[4:]}")
        print("\n  → 세대 간 통신 정상! 로봇이 그 토픽들을 정말 안 쏘는 것.")
        print("     다음: 로봇이 실제로 쏘는 토픽명 조회 (2차 수단 안내)")
    elif sub.returncode == 42:
        print("  [무수신]   신세대 구독자가 구세대 발행을 못 들음")
        if pub_err:
            print(f"             (발행자 오류 확인: {pub_err[-1][:70]})")
        else:
            print("             (발행자는 무사히 6초 발행함)")
        print("\n  → 세대 간 짝맺기 실패 확정 — Python 3.11 릴레이로 확정 전환")
    else:
        tail = (sub.stderr or "").strip().splitlines()
        print(f"  [크래시]   {(tail[-1] if tail else f'code={sub.returncode}')[:70]}")


if __name__ == "__main__":
    main()
