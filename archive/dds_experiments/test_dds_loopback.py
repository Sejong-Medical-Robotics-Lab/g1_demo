#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_dds_loopback.py — 구독 경로 고장의 소재 판정 (로봇 불필요)

넷 다 buffer overflow 로 터진 상황: 로봇 메시지 문제인지, 이 PC 의
DDS 라이브러리(CycloneDDS 빌드 ↔ sdk2py 바인딩) 문제인지 가른다.

방법: 이 PC 가 가짜 SportModeState 를 스스로 발행하고 스스로 구독.
로봇이 전혀 관여하지 않으므로 —
    [크래시]  → 100% 로컬 라이브러리 문제 (CycloneDDS 버전 불일치 유력)
                → 오디오 크래시도 같은 뿌리였을 가능성
    [수신 OK] → 로컬은 정상, 로봇 쪽 메시지가 진짜 특이 케이스

사용:
    python3 test_dds_loopback.py --iface $G1_IFACE
"""
import argparse
import subprocess
import sys
import textwrap
import time

PUB = textwrap.dedent("""
    import time
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelPublisher
    from unitree_sdk2py.idl.unitree_go.msg.dds_ import SportModeState_
    from unitree_sdk2py.idl.default import unitree_go_msg_dds__SportModeState_

    ChannelFactoryInitialize(0, "{iface}")
    pub = ChannelPublisher("rt/loopback_test", SportModeState_)
    pub.Init()
    msg = unitree_go_msg_dds__SportModeState_()
    msg.position[0] = 1.23
    msg.position[1] = 4.56
    for _ in range(60):          # 6초간 10Hz
        pub.Write(msg)
        time.sleep(0.1)
""")

SUB = textwrap.dedent("""
    import sys, time
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
    from unitree_sdk2py.idl.unitree_go.msg.dds_ import SportModeState_

    got = []
    def cb(m):
        if not got:
            got.append(f"pos=({{m.position[0]:.2f}},{{m.position[1]:.2f}})")

    ChannelFactoryInitialize(0, "{iface}")
    sub = ChannelSubscriber("rt/loopback_test", SportModeState_)
    sub.Init(cb, 10)
    t0 = time.time()
    while time.time() - t0 < 5 and not got:
        time.sleep(0.1)
    if got:
        print("HIT " + got[0]); sys.exit(0)
    sys.exit(42)
""")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iface", required=True)
    args = ap.parse_args()
    if not args.iface.strip():
        sys.exit("\n  [중단] --iface 비어 있음 — export G1_IFACE=enx... 후 재실행\n")

    print("  발행자(자식1) + 구독자(자식2) 기동 — 로봇 무관, PC 자가 통신\n")
    pub = subprocess.Popen([sys.executable, "-c", PUB.format(iface=args.iface)],
                           stderr=subprocess.PIPE, text=True)
    time.sleep(1.0)              # 발행자 먼저 자리잡게
    sub = subprocess.run([sys.executable, "-c", SUB.format(iface=args.iface)],
                         capture_output=True, text=True, timeout=15)
    pub.terminate()
    pub_err = (pub.stderr.read() or "").strip().splitlines()

    if sub.returncode == 0 and sub.stdout.startswith("HIT"):
        print(f"  [수신 OK]  {sub.stdout.strip()[4:]}")
        print("\n  → 로컬 DDS 는 정상. 문제는 로봇 쪽 메시지 형식 — 2차 수단(타입명 조회)으로")
    elif sub.returncode == 42:
        print("  [무수신]   구독자는 안 죽었지만 데이터가 안 옴")
        if pub_err:
            print(f"             발행자 쪽 오류: {pub_err[-1][:70]}")
        print("\n  → 발행자가 죽었는지 위 오류 확인. 발행자도 크래시면 아래 [크래시] 판정과 동일")
    else:
        tail = (sub.stderr or "").strip().splitlines()
        print(f"  [크래시]   {(tail[-1] if tail else f'code={sub.returncode}')[:70]}")
        print("\n  → 로봇 무관, 100% 이 PC 의 라이브러리 문제.")
        print("     다음 진단 두 줄을 실행해 결과 공유:")
        print("       ls ~/cyclonedds/install/lib | grep libddsc")
        print("       python3 -c \"import cyclonedds; print(cyclonedds.__version__)\"")


if __name__ == "__main__":
    main()
