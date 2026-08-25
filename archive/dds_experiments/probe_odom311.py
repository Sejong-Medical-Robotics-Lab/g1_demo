#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_odom311.py — [3.11 전용] — G1 내장 오도메트리 후보 (토픽, 타입) 자동 탐침

rt/odommodestate + Go2 SportModeState 조합이 buffer overflow 로 터짐
= 토픽은 살아있는데 메시지 구조가 다르다는 뜻. 후보 조합들을
**각각 자식 프로세스로 격리**해 시험한다 — 터져도 다음으로 넘어감.

사용:
    python3 probe_odom.py --iface $G1_IFACE

결과 읽는 법:
    [수신 OK]   ← 이 조합이 정답. 필드 샘플까지 출력됨
    [무수신]    ← 그 토픽에 그 타입 구독은 됐지만 데이터 없음
    [크래시]    ← 구조 불일치 (기존 증상 재현)
"""
import argparse
import subprocess
import sys
import textwrap

CANDIDATES = [
    # (토픽, sdk2py 타입 경로, 타입 클래스명, 위치필드 출력식)
    ("rt/odommodestate", "unitree_sdk2py.idl.unitree_go.msg.dds_", "SportModeState_",
     "f'pos=({m.position[0]:+.3f},{m.position[1]:+.3f})'"),
    ("rt/sportmodestate", "unitree_sdk2py.idl.unitree_go.msg.dds_", "SportModeState_",
     "f'pos=({m.position[0]:+.3f},{m.position[1]:+.3f})'"),
    ("rt/lf/odommodestate", "unitree_sdk2py.idl.unitree_go.msg.dds_", "SportModeState_",
     "f'pos=({m.position[0]:+.3f},{m.position[1]:+.3f})'"),
    # G1(휴머노이드, hg) 저수준 상태 — 위치는 없지만 통신 경로 검증 +
    # IMU 라도 확인 (여기가 되면 hg 계열 타입이 정답 계통이라는 뜻)
    ("rt/lowstate", "unitree_sdk2py.idl.unitree_hg.msg.dds_", "LowState_",
     "f'imu_rpy=({m.imu_state.rpy[0]:+.2f},{m.imu_state.rpy[1]:+.2f},{m.imu_state.rpy[2]:+.2f})'"),
]

CHILD = textwrap.dedent("""
    import sys, time, signal
    signal.signal(signal.SIGALRM, lambda *a: sys.exit(42))
    signal.alarm(7)
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
    from {mod} import {cls}

    got = []
    def cb(m):
        if not got:
            try:
                got.append({expr})
            except Exception as e:
                got.append(f"(필드 접근 실패: {{e}})")

    ChannelFactoryInitialize(0, "{iface}")
    sub = ChannelSubscriber("{topic}", {cls})
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
        sys.exit("\n  [중단] --iface 가 비어 있습니다. 인터페이스 이름이 바뀐 것:\n"
                 "         ip link show | grep enx   → 나온 이름으로\n"
                 "         export G1_IFACE=enx...    후 재실행\n")

    print(f"  후보 {len(CANDIDATES)}개, 각 5초씩 격리 시험 (리스너 방식, venv311 전용)\n")
    hits = []
    for topic, mod, cls, expr in CANDIDATES:
        code = CHILD.format(mod=mod, cls=cls, expr=expr,
                            iface=args.iface, topic=topic)
        try:
            r = subprocess.run([sys.executable, "-c", code],
                               capture_output=True, text=True, timeout=20)
        except subprocess.TimeoutExpired:
            print(f"  [무수신]   {topic}  ×  {cls}   (Read 무한대기 — 짝맺기 실패)")
            continue
        label = f"{topic}  ×  {cls}"
        if r.returncode == 0 and r.stdout.startswith("HIT"):
            print(f"  [수신 OK]  {label}")
            print(f"             {r.stdout.strip()[4:]}")
            hits.append((topic, cls))
        elif r.returncode == 42:
            print(f"  [무수신]   {label}")
        else:
            sig = (r.stderr or "").strip().splitlines()
            tail = sig[-1] if sig else f"code={r.returncode}"
            print(f"  [크래시]   {label}   ({tail[:60]})")

    print()
    if hits:
        print("  → 정답 조합 발견! 위 [수신 OK] 조합을 알려주면 g1_odom_bridge 를 맞춰 고침")
    else:
        print("  → 전부 실패. 다음 수: ros2+cyclonedds 로 토픽·타입명 직접 조회 (안내 예정)")


if __name__ == "__main__":
    main()
