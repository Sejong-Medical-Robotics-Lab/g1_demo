#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_fsm_probe.py — FSM ID 를 직접 하나씩 보내 전이 사슬을 찾아내는 도구.

왜 필요한가:
  SDK 의 LocoClient 에는 Damp(1) / Start(500) / Squat2StandUp(706) /
  Lie2StandUp(702) / Sit(3) / ZeroTorque(0) 래퍼밖에 없다.
  G1 문서에 나오는 **Lock Stand(잠금 기립)** 에 해당하는 함수가 없어서,
  Damp 에서 곧바로 706 을 보내면 로봇이 조용히 거부한다.
  (SetFsmId 는 0 을 반환한다 — RPC 접수와 실제 전이는 별개다.)

  따라서 우리 기체에서 실제로 통하는 사슬을 실측으로 찾아야 한다.
  이 스크립트는 한 번에 하나의 FSM ID 만 보내고, 결과를 관찰한다.

사용:
  python3 g1_fsm_probe.py --iface wlo1              # 대화형(추천)
  python3 g1_fsm_probe.py --iface wlo1 --fsm 4      # 한 번만 보내고 종료
  python3 g1_fsm_probe.py --iface wlo1 --watch      # 아무것도 안 보내고 FSM 만 관찰

안전:
  - 매 전송 전에 확인을 받는다.
  - Ctrl+C 또는 'd' 입력 시 즉시 Damp.
  - 행어 거치와 리모컨 대기 없이는 실행하지 않는다.
"""
import argparse
import sys
import time

from g1_common import G1Link, banner, gate, safe_exit

# G1 에서 알려진/추정되는 FSM ID.
# ※ '추정' 표시는 SDK 에 래퍼가 없어 문서·관례로만 아는 값이다 — 이 스크립트로 확인한다.
CANDIDATES = [
    (0,   "ZeroTorque — 완전 무력",                "SDK: ZeroTorque()"),
    (1,   "Damp — 감쇠(안전 상태)",                 "SDK: Damp()"),
    (2,   "Squat — 쭈그림",                        "추정 (래퍼 없음)"),
    (3,   "Sit — 앉기",                            "SDK: Sit()"),
    (4,   "Lock Stand — 잠금 기립  ★ 유력 후보",     "추정 (래퍼 없음)"),
    (200, "Main Control — 메인 제어  ★ 유력 후보",   "추정 (래퍼 없음)"),
    (500, "Start — SDK 가 부르는 메인 제어",         "SDK: Start()"),
    (702, "Lie2StandUp — 누운 상태에서 기립",        "SDK: Lie2StandUp()"),
    (706, "Squat2StandUp — 쭈그림↔기립 토글",        "SDK: Squat2StandUp()"),
]

# 실측 우선순위 — Damp 이후 이 순서로 시도해 보기를 권장한다.
SUGGESTED = [4, 200, 500, 706]


def observe(link, sec, label=""):
    """전송 후 FSM 변화를 관찰한다. 마지막 관측값을 반환."""
    t0 = time.monotonic()
    seen = None
    changes = []
    while time.monotonic() - t0 < sec:
        cur = link.fsm()
        if cur != seen:
            changes.append((time.monotonic() - t0, cur))
            seen = cur
        print(f"      … {label} 관찰 {time.monotonic() - t0:4.1f}s / FSM: "
              f"{cur if cur is not None else '조회 불가'}   ", end="\r", flush=True)
        time.sleep(0.3)
    print(" " * 60, end="\r")
    if changes:
        print("      FSM 변화:", " → ".join(
            f"{v}@{t:.1f}s" for t, v in changes))
    else:
        print("      FSM 변화 없음")
    return seen


def send(link, fsm_id, sec):
    label = next((d for i, d, _ in CANDIDATES if i == fsm_id), f"FSM {fsm_id}")
    before = link.fsm()
    print(f"\n  전송 전 상태: {link.state_text()}")
    print(f"  → SetFsmId({fsm_id})  [{label}]")

    code = link.loco.SetFsmId(fsm_id)
    print(f"      반환 코드: {code}  "
          f"{'(접수됨 — 단, 실제 전이는 아래 관찰로 판정)' if code == 0 else '(거부)'}")

    after = observe(link, sec, f"FSM {fsm_id}")
    print(f"      전송 후 상태: {link.state_text()}")

    # ※ 실기체에서 GetFsmId 가 SetFsmId 의 번호와 일치하지 않는 것이 관측됐다
    #   (4 로 전이했는데도 200 으로 읽힘). 그래서 조회값만으로는 판정하지 않고,
    #   눈으로 본 결과를 물어 대응표를 만든다.
    print("\n      조회값은 SetFsmId 번호와 다를 수 있습니다 — 눈으로 판정하세요.")
    seen = input("      로봇이 실제로 어떻게 되었습니까? "
                 "(1=목표 자세로 바뀜 / 2=변화 없음 / 3=다른 자세) > ").strip()
    verdict = {"1": "목표 자세 도달", "2": "변화 없음", "3": "다른 자세"}.get(seen, "미기록")
    print(f"\n      ★ 기록: SetFsmId({fsm_id}) → 육안 '{verdict}' / "
          f"조회 fsm_id={after}, mode={link.fsm_mode()}")
    return after


def main():
    ap = argparse.ArgumentParser(description="G1 FSM 전이 사슬 실측 도구")
    ap.add_argument("--iface", help="예: wlo1 (CYCLONEDDS_URI 설정 시 생략 가능)")
    ap.add_argument("--domain", type=int, default=0)
    ap.add_argument("--fsm", type=int, help="이 FSM ID 하나만 보내고 종료")
    ap.add_argument("--watch", action="store_true", help="전송 없이 FSM 만 관찰")
    ap.add_argument("--sec", type=float, default=8.0, help="전송 후 관찰 시간")
    args = ap.parse_args()

    banner("FSM 전이 사슬 실측 — 한 번에 하나씩만 보낸다")

    link = G1Link(args.iface, args.domain, with_arm=False)

    if args.watch:
        print("\n  FSM 관찰 모드 (Ctrl+C 종료)\n")
        try:
            while True:
                print(f"      FSM: {link.fsm_text()}        ", end="\r", flush=True)
                time.sleep(0.3)
        except KeyboardInterrupt:
            print("\n  종료.")
        return

    print(f"\n  현재 FSM: {link.fsm_text()}")
    print("\n  알려진 FSM ID")
    for i, desc, src in CANDIDATES:
        print(f"    {i:>3d}  {desc:<34s} {src}")
    print(f"\n  권장 시도 순서 (Damp 이후): {' → '.join(str(i) for i in SUGGESTED)}")

    gate("행어 거치 + 리모컨(비상 Damp) 대기 상태입니까?")

    try:
        if args.fsm is not None:
            gate(f"SetFsmId({args.fsm}) 를 보냅니다. 진행합니까?")
            send(link, args.fsm, args.sec)
            return

        # 대화형
        print("\n  숫자=해당 FSM 전송 / d=Damp / q=종료")
        while True:
            raw = input(f"\n[FSM {link.fsm()}] 보낼 ID > ").strip().lower()
            if raw in ("q", "quit", "exit"):
                print("  종료 — 로봇 상태를 확인하세요.")
                break
            if raw == "d":
                link.damp()
                observe(link, 4.0, "Damp")
                continue
            if not raw.lstrip("-").isdigit():
                print("  숫자 또는 d / q 를 입력하세요.")
                continue
            fsm_id = int(raw)
            gate(f"SetFsmId({fsm_id}) 를 보냅니다. 로봇이 움직일 수 있습니다. 진행합니까?")
            send(link, fsm_id, args.sec)

    except KeyboardInterrupt:
        safe_exit(link, "Ctrl+C 중단")
    except Exception as e:
        safe_exit(link, f"예외 {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
