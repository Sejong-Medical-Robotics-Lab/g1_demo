#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_stand_test.py — 1단계: Damp → 기립 → 균형 제어 단독 검증.

시퀀스에 통합하기 전에 '전이만' 떼어내서 실기체에서 확인하는 스크립트다.
개발 원칙: 각 기능을 독립적으로 검증한 뒤 g1_real_sequence.py 에 통합한다.

사용:
  python3 g1_stand_test.py --dry-run                    # 로봇 없이 계획만 출력
  python3 g1_stand_test.py --iface enp2s0               # 전이만
  python3 g1_stand_test.py --iface enp2s0 --with-arm    # 전이 + 상체 1개(hands up)
  python3 g1_stand_test.py --iface enp2s0 --audio         # 음성·LED 안내 켜기
  python3 g1_stand_test.py --iface enp2s0 --list-actions

전제: 행어 거치 + 멘토 리모컨(비상 Damp) 확인 없이는 실행하지 않는다.
"""
import argparse
import sys
import time

from g1_common import (FSM, AbortRun, G1Link, RealCommandError, banner,
                       call_text, countdown, gate, safe_damp)

# 전이 표 — (라벨, FSM ID, 기대 관측값 집합, 최소 안정화[s], 최대 대기[s])
#
# ※ 706 은 Squat2StandUp 과 StandUp2Squat 이 '공유'하는 ID다(토글).
#   따라서 이미 서 있는 상태에서 다시 706 을 보내면 앉을 수 있다.
#   기대 관측값은 펌웨어에 따라 다를 수 있으므로, 실기체에서 관측한 값을
#   아래 EXPECT 에 반영하고 조에 인수인계할 것. ← 1단계의 핵심 산출물
TRANSITIONS = [
    ("Damp — 힘 빼기(알려진 안전 상태)", FSM.DAMP,         {1},        3.0,  8.0),
    ("기립 전이(위치잠금 기립)",          FSM.SQUAT_TOGGLE, {4, 706},   6.0, 15.0),
    ("메인 컨트롤(균형 제어) 진입",        FSM.START,        {500, 200}, 5.0, 12.0),
]

ARM_DEMO = "hands up"   # --with-arm 일 때 실행할 팔 액션

# --audio 일 때 각 전이에서 말할 문구·LED (FSM ID → (문구, LED 상태))
SPEECH = {
    1:   ("댐프 모드로 전환합니다.", "damp"),
    706: ("기립합니다.",             "standing"),
    500: ("균형 제어 상태입니다.",    "balance"),
}


def do_transition(link, label, fsm_id, expect, settle, timeout):
    banner(f"전이: {label}  (SetFsmId {fsm_id})")
    print(f"  현재 FSM: {link.fsm_text()}")
    gate(f"멘토 승인 — '{label}' 실행해도 됩니까?")
    text, color = SPEECH.get(fsm_id, (None, None))
    if text:
        link.announce(text, color)       # 오디오 없으면 조용히 무시된다
    link.set_fsm(fsm_id, label)          # ← 반환 코드 검사됨
    call_text(f"{label} — SetFsmId({fsm_id}) 전송")
    link.wait_fsm(expect, settle, timeout, label)
    ans = input(f'[확인] "{label}" 완료를 육안으로 확인했습니까? '
                f"(y=계속 / 그 외=즉시 Damp) > ").strip().lower()
    if ans != "y":
        raise AbortRun(f"{label} 육안 확인 실패")


def main():
    ap = argparse.ArgumentParser(description="1단계 — Damp/기립/균형 단독 검증")
    ap.add_argument("--iface", help="로봇이 연결된 인터페이스 (예: enp2s0)")
    ap.add_argument("--domain", type=int, default=0)
    ap.add_argument("--with-arm", action="store_true",
                    help=f"기립 후 팔 액션 '{ARM_DEMO}' 1회 실행")
    ap.add_argument("--audio", action="store_true",
                    help="각 단계에서 음성 안내 + LED 색 표시")
    ap.add_argument("--volume", type=int, default=70, help="--audio 볼륨 0~100")
    ap.add_argument("--dry-run", action="store_true", help="로봇·SDK 없이 계획만")
    ap.add_argument("--list-actions", action="store_true",
                    help="action_map + 실기체 GetActionList 대조 후 종료")
    args = ap.parse_args()

    banner("1단계 — Damp → 기립 → 균형 제어 (행어 · 멘토 확인 하)")
    print("\n  실행 계획")
    for i, (label, fid, exp, settle, tout) in enumerate(TRANSITIONS, 1):
        print(f"   {i}. {label:<32s} SetFsmId({fid})  기대 {sorted(exp)}")
    if args.with_arm:
        print(f"   4. 팔 액션 '{ARM_DEMO}' → release arm")
    print("   종료. Damp 또는 기립 유지 선택")

    if args.dry_run:
        print("\n  --dry-run: 여기까지가 실행 전 코드 리뷰용 출력입니다.")
        return
    if not args.iface:
        sys.exit("--iface 가 필요합니다 (예: --iface enp2s0). 리뷰만 하려면 --dry-run.")

    link = G1Link(args.iface, args.domain, with_arm=True,
                  with_audio=args.audio,
                  volume=args.volume if args.audio else None)

    if args.list_actions:
        print("\n  SDK action_map:")
        for k, v in sorted(link.action_map.items(), key=lambda kv: kv[1]):
            print(f"    {v:>3d}  {k}")
        print("\n  실기체 GetActionList 응답:")
        print("   ", link.action_list() or "(조회 실패 — 균형 제어 상태에서 재시도)")
        return

    # ── 실행 전 게이트 ──
    gate("행어 거치 확인 완료? — 발은 지면, 하중은 다리, 스트랩은 느슨")
    gate("멘토가 리모컨(비상 Damp) 소지 중이고 즉시 조작 가능한 위치입니까?")
    gate("모니터링 담당이 g1_real_monitor.py watch 가동 중입니까?")

    t0 = time.monotonic()
    try:
        print(f"\n  연결 확인 — 현재 FSM: {link.fsm_text()}")
        for label, fid, exp, settle, tout in TRANSITIONS:
            do_transition(link, label, fid, exp, settle, tout)
            if fid == FSM.DAMP:
                call_text("Damp 확인 — 상태 정상 콜 요청")
                gate("모니터링 담당의 '상태 정상' 콜을 받았습니까?")

        call_text("기립 완료 — 균형 유지 상태")
        print(f"\n  관측 FSM: {link.fsm_text()}")
        print("  ※ 이 값을 TRANSITIONS 의 기대값에 반영하고 조에 인수인계할 것")

        if args.with_arm:
            banner(f"상체 확인 — 팔 액션 '{ARM_DEMO}'")
            gate(f"멘토 승인 — '{ARM_DEMO}' 실행해도 됩니까?")
            link.announce("양팔을 들겠습니다.", "arm")
            link.arm_action(ARM_DEMO)
            countdown(8.0, ARM_DEMO)
            link.release_arm()
            print("      release arm 전송 — 팔 제어 반납 완료")

        # 안정 유지 관찰
        banner("안정성 관찰 — 30초간 균형 유지 확인 (Ctrl+C 로 즉시 중단)")
        t_end = time.monotonic() + 30.0
        while time.monotonic() < t_end:
            print(f"      … 남은 {t_end - time.monotonic():4.1f}s / "
                  f"FSM {link.fsm_text()}   ", end="\r", flush=True)
            time.sleep(1.0)
        print()
        link.announce("1단계 검증을 마쳤습니다.", "balance")
        call_text("1단계 검증 완료")

        while True:
            c = input("\n[종료] d=Damp(행어 하중·멘토 승인) / k=기립 유지 > ").strip().lower()
            if c == "d":
                gate("멘토 승인 — Damp 로 종료합니까? (행어 스트랩 하중 확인 준비)")
                link.announce("댐프 모드로 종료합니다.", "damp")
                link.damp()
                call_text("Damp 확인 — 종료 절차 진행")
                break
            if c == "k":
                print("  기립(균형) 유지 상태로 종료 — 다음 실행자에게 인계.")
                break

    except KeyboardInterrupt:
        safe_damp(link, "Ctrl+C 중단")
    except AbortRun as e:
        safe_damp(link, str(e))
    except RealCommandError as e:
        safe_damp(link, str(e))
    except Exception as e:
        safe_damp(link, f"예외 {type(e).__name__}: {e}")
    finally:
        print(f"\n  소요 {time.monotonic() - t0:.0f}s — 관측 FSM 값을 기록하세요.")


if __name__ == "__main__":
    main()
