#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_dds_loopback_poll.py — 폴링 방식 구독 루프백 (설치 불필요 우회 시험)

지금까지의 크래시는 전부 콜백(리스너) 방식 sub.Init(handler, n) 에서
났다. sdk2py 에는 콜백 없이 sub.Init() 후 sub.Read(timeout) 로 직접
꺼내오는 폴링 방식도 있다 — 터지는 지점이 리스너 생성 경로라면
폴링은 무사할 수 있다.

    [수신 OK] → 폴링으로 전환하면 끝. B안 코드 몇 줄 수정으로 재개
    [크래시]  → 리스너만의 문제가 아님 → 다음 사다리(0.11 시험 → 3.11 릴레이)

사용:  python3 test_dds_loopback_poll.py --iface $G1_IFACE
       (venv_dds 든 기존 venv 든 무관 — 어디서든 시험 가치 있음)
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
    for _ in range(60):
        pub.Write(msg)
        time.sleep(0.1)
""")

SUB_POLL = textwrap.dedent("""
    import sys, time
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
    from unitree_sdk2py.idl.unitree_go.msg.dds_ import SportModeState_

    ChannelFactoryInitialize(0, "{iface}")
    sub = ChannelSubscriber("rt/loopback_test", SportModeState_)
    sub.Init()                     # ★ 콜백 없음 — 폴링 모드
    t0 = time.time()
    while time.time() - t0 < 5:
        m = sub.Read(200)          # 200ms 대기 폴링
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

    print("  폴링 방식 구독 시험 (콜백/리스너 경로 완전 우회)\n")
    pub = subprocess.Popen([sys.executable, "-c", PUB.format(iface=args.iface)],
                           stderr=subprocess.PIPE, text=True)
    time.sleep(1.0)
    sub = subprocess.run([sys.executable, "-c", SUB_POLL.format(iface=args.iface)],
                         capture_output=True, text=True, timeout=15)
    pub.terminate()

    if sub.returncode == 0 and sub.stdout.startswith("HIT"):
        print(f"  [수신 OK]  {sub.stdout.strip()[4:]}")
        print("\n  → 폴링은 살아있다! B안 코드를 폴링으로 바꿔서 재개")
    elif sub.returncode == 42:
        print("  [무수신]   폴링 구독자는 생존했지만 데이터 없음")
        err = (pub.stderr.read() or "").strip().splitlines()
        if err:
            print(f"             발행자 오류: {err[-1][:70]}")
    else:
        tail = (sub.stderr or "").strip().splitlines()
        print(f"  [크래시]   {(tail[-1] if tail else f'code={sub.returncode}')[:70]}")
        print("\n  → 폴링도 아웃. 다음: 0.11 바인딩 1회 시험 → 안 되면 3.11 릴레이")


if __name__ == "__main__":
    main()
