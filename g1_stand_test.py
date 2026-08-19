#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_stand_test.py — 1단계: Damp → 잠금 기립 → 레귤러 모드 단독 검증.

전원을 켠 직후(FSM 0)부터 이 스크립트 하나로 다음 상태까지 끌어올린다:

    0 (전원 인가)  →  1 Damp  →  4 Lock Stand(레디)  →  레귤러 모드

레귤러 모드는 조이스틱 R1+Y 로 들어가는 그 모드이고, SDK 쪽 이름은
메인 컨트롤이다. 보행과 팔 액션은 이 상태에서만 동작한다.
스크립트는 기본적으로 **Damp 로 내리지 않고 그대로 종료**하므로,
끝나자마자 상체 명령이나 보행 테스트를 바로 이어서 실행할 수 있다.

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
                       call_text, countdown, gate, manual_confirm, safe_exit)

# 전이 표 — (라벨, FSM ID, 기대 관측값 집합, 최소 안정화[s], 최대 대기[s])
#
# 실기체 관측으로 확정한 사슬:  0(전원 인가) → 1(Damp) → 4(Lock Stand) → 500/200
#
# ※ 0 은 '보내는' 값이 아니다. 전원을 넣으면 로봇이 그 상태로 시작할 뿐이고,
#   서 있는 상태에서 0(ZeroTorque)을 보내면 힘이 완전히 빠져 주저앉는다.
# ※ 706(Squat2StandUp)은 Damp 직후에는 거부된다(SetFsmId 는 0 을 반환하지만
#   FSM 이 바뀌지 않는다). 쭈그린 자세에서만 유효한 토글이라, 기립 경로는 4 다.
# ※ SDK 의 LocoClient 에는 4 에 해당하는 래퍼가 없어 SetFsmId(4) 로 직접 보낸다.
TRANSITIONS = [
    ("Damp — 힘 빼기(알려진 안전 상태)", FSM.DAMP,       {1}, 3.0,  8.0),
    ("Lock Stand — 잠금 기립(레디)",      FSM.LOCK_STAND, {4}, 6.0, 15.0),
]

# 레귤러 모드 = 조이스틱 R1+Y 로 들어가는 그 모드 = SDK 의 메인 컨트롤.
# 보행과 팔 액션은 이 상태에서만 동작하므로 기본 사슬에 포함한다.
#
# ★ 실기체 실측(2026-08): 레귤러 모드 = FSM 200.
#   SDK 의 Start()(=500)는 이 기체에서 통하지 않는다(FSM 이 4 에서 안 바뀜).
#   따라서 200 을 쓰고, 500 은 다른 기체·펌웨어를 위한 예비 후보로만 남긴다.
REGULAR_LABEL = "레귤러 모드(메인 컨트롤) 진입 — R1+Y 와 같은 모드"
REGULAR_CANDIDATES = [FSM.MAIN_CONTROL]              # 확정값 200 (예비: FSM.START=500)
REGULAR_EXPECT = {200, 500}
REGULAR_SETTLE, REGULAR_TIMEOUT = 5.0, 12.0

ARM_DEMO = "hands up"   # --with-arm 일 때 실행할 팔 액션

# --audio 일 때 각 전이에서 말할 문구·LED (FSM ID → (문구, LED 상태))
SPEECH = {
    1:   ("댐프 모드로 전환합니다.", "damp"),
    4:   ("기립합니다.",             "standing"),
    200: ("균형 제어 상태입니다.",    "balance"),
    500: ("균형 제어 상태입니다.",    "balance"),
}


def do_transition(link, label, fsm_id, expect, settle, timeout):
    banner(f"전이: {label}  (SetFsmId {fsm_id})")
    print(f"  현재 FSM: {link.fsm_text()}")
    gate(f"멘토 승인 — '{label}' 실행해도 됩니까?")
    text, color = SPEECH.get(fsm_id, (None, None))
    if color:
        link.led(color)                  # 안내 음성은 로봇 내장 음성이 담당

    manual = False
    try:
        link.set_fsm(fsm_id, label)      # ← 반환 코드 검사됨
    except RealCommandError as e:
        if not e.timeout:
            raise                        # 진짜 거부 — 사람이 확인해도 진행 불가
        # 응답만 유실된 경우: 명령은 로봇에 도착했을 수 있다. 작업자 판정에 맡긴다.
        print(f"\n  {e}")
        if not manual_confirm(label, "응답 시간 초과"):
            raise AbortRun(f"{label} — 통신 확인 실패, 작업자도 확인 못함")
        manual = True

    call_text(f"{label} — SetFsmId({fsm_id}) 전송"
              + ("  [작업자 육안 확인]" if manual else ""))
    if not manual and not link.wait_fsm(expect, settle, timeout, label):
        if link.fsm() is None and not manual_confirm(label, "FSM 조회 불가"):
            raise AbortRun(f"{label} — 상태 확인 실패")
    ans = input(f'[확인] "{label}" 완료를 육안으로 확인했습니까? '
                f"(y=계속 / 그 외=즉시 Damp) > ").strip().lower()
    if ans != "y":
        raise AbortRun(f"{label} 육안 확인 실패")


def do_regular_mode(link):
    """레귤러 모드 진입 — 후보 FSM 을 순서대로 시도한다."""
    banner(f"전이: {REGULAR_LABEL}")
    print(f"  현재 FSM: {link.fsm_text()}")
    gate("멘토 승인 — 레귤러 모드(보행 가능 상태)로 진입해도 됩니까?")
    link.led("balance")     # 음성 안내는 로봇 내장 음성이 담당한다

    for k, fsm_id in enumerate(REGULAR_CANDIDATES, 1):
        before = link.fsm()
        print(f"\n  시도 {k}/{len(REGULAR_CANDIDATES)} — SetFsmId({fsm_id})")
        manual = False
        try:
            link.set_fsm(fsm_id, f"레귤러 모드({fsm_id})")
        except RealCommandError as e:
            if not e.timeout:
                print(f"      거부됨: {e}")
                continue
            print(f"\n      {e}")
            if not manual_confirm(REGULAR_LABEL, "응답 시간 초과"):
                continue
            manual = True
        if manual:
            print("      → 작업자 육안 확인으로 진행")
            return True
        if link.wait_fsm(REGULAR_EXPECT, REGULAR_SETTLE, REGULAR_TIMEOUT, "레귤러 모드"):
            print(f"      ★ 레귤러 모드 = FSM {link.fsm()} (SetFsmId({fsm_id}))")
            print("        이 값을 REGULAR_CANDIDATES 에 단독으로 남기고 인수인계할 것")
            return True
        if link.fsm() != before:
            print(f"      FSM 이 {before} → {link.fsm()} 로 바뀌었으나 기대값과 다름")
    print("\n  [주의] 후보를 모두 시도했지만 레귤러 모드 확인 실패 — 육안/리모컨으로 판정")
    ans = input("[확인] 로봇이 레귤러 모드로 보입니까? (y=계속 / 그 외=중단) > ").strip().lower()
    if ans != "y":
        raise AbortRun("레귤러 모드 진입 실패")
    return False


def main():
    ap = argparse.ArgumentParser(description="1단계 — Damp/기립/레귤러 모드")
    ap.add_argument("--iface", help="로봇이 연결된 인터페이스 (예: enp2s0)")
    ap.add_argument("--domain", type=int, default=0)
    ap.add_argument("--with-arm", action="store_true",
                    help=f"레귤러 모드 진입 후 팔 액션 '{ARM_DEMO}' 1회 실행")
    ap.add_argument("--no-regular", action="store_true",
                    help="레귤러 모드 진입을 생략하고 잠금 기립(4)에서 멈춤")
    ap.add_argument("--exit", choices=["keep", "damp", "ask"], default="keep",
                    help="종료 방식: keep=현재 자세 유지(기본) / damp=Damp / ask=물어봄")
    ap.add_argument("--audio", action="store_true",
                    help="LED 색으로 상태 표시 (음성은 로봇 내장 음성이 담당)")
    ap.add_argument("--tts", action="store_true",
                    help="우리 문구를 TTS 로 읽게 함 — 한국어 미지원이라 기본 꺼짐")
    ap.add_argument("--volume", type=int, default=70, help="--audio 볼륨 0~100")
    ap.add_argument("--dry-run", action="store_true", help="로봇·SDK 없이 계획만")
    ap.add_argument("--list-actions", action="store_true",
                    help="action_map + 실기체 GetActionList 대조 후 종료")
    args = ap.parse_args()

    banner("1단계 — Damp → 잠금 기립 → 레귤러 모드 (행어 · 멘토 확인 하)")
    print("\n  실행 계획")
    for i, (label, fid, exp, settle, tout) in enumerate(TRANSITIONS, 1):
        print(f"   {i}. {label:<32s} SetFsmId({fid})  기대 {sorted(exp)}")
    if not args.no_regular:
        print(f"   {len(TRANSITIONS)+1}. {REGULAR_LABEL}")
        print(f"      SetFsmId 후보 {REGULAR_CANDIDATES} 순서대로 시도, "
              f"기대 {sorted(REGULAR_EXPECT)}")
    if args.with_arm:
        print(f"   {len(TRANSITIONS)+2}. 팔 액션 '{ARM_DEMO}' → release arm")
    print(f"   종료 정책: {args.exit}"
          f"  ({'현재 자세 유지' if args.exit == 'keep' else 'Damp 로 종료' if args.exit == 'damp' else '종료 시 선택'})")

    if args.dry_run:
        print("\n  --dry-run: 여기까지가 실행 전 코드 리뷰용 출력입니다.")
        return
    if not args.iface:
        sys.exit("--iface 가 필요합니다 (예: --iface enp2s0). 리뷰만 하려면 --dry-run.")

    link = G1Link(args.iface, args.domain, with_arm=True,
                  with_audio=args.audio or args.tts, tts=args.tts,
                  volume=args.volume if (args.audio or args.tts) else None)

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

        if not args.no_regular:
            do_regular_mode(link)

        call_text("기립 완료 — 레귤러 모드 유지 상태")
        print(f"\n  관측 FSM: {link.fsm_text()}")
        print("  ※ 이 값을 TRANSITIONS 의 기대값에 반영하고 조에 인수인계할 것")

        if args.with_arm and args.no_regular:
            print("\n  [건너뜀] 팔 액션은 레귤러 모드에서만 동작합니다 — "
                  "--no-regular 를 빼고 실행하세요.")
        elif args.with_arm:
            banner(f"상체 확인 — 팔 액션 '{ARM_DEMO}'")
            gate(f"멘토 승인 — '{ARM_DEMO}' 실행해도 됩니까?")
            link.led("arm")
            link.arm_action(ARM_DEMO)
            countdown(8.0, ARM_DEMO)
            link.release_arm()
            print("      release arm 전송 — 팔 제어 반납 완료")

        # 안정 유지 관찰
        banner("안정성 관찰 — 30초간 균형 유지 확인 (Ctrl+C 로 즉시 중단)")
        # 무선 링크에서는 매초 GetFsmId(RPC 왕복)를 걸면 타임아웃이 잦다.
        # 3초에 한 번만 조회하고, 실패해도 관찰을 계속한다.
        t_end = time.monotonic() + 30.0
        shown = "…"
        last_poll = 0.0
        while time.monotonic() < t_end:
            if time.monotonic() - last_poll > 3.0:
                try:
                    shown = link.fsm_text()
                except Exception:
                    shown = "조회 실패(통신)"
                last_poll = time.monotonic()
            print(f"      … 남은 {t_end - time.monotonic():4.1f}s / FSM {shown}   ",
                  end="\r", flush=True)
            time.sleep(0.5)
        print()
        link.led("balance")
        call_text("1단계 검증 완료")

        if args.exit == "keep":
            link.release_arm()
            print(f"\n  현재 자세 유지로 종료 — FSM {link.fsm_text()}")
            print("  로봇은 레귤러 모드로 서 있습니다. 이어서 바로 실행 가능:")
            print("    python3 g1_real_sequence.py --iface <IF> --arm-only --audio")
            print("    python3 g1_walk_test.py     --iface <IF> --vx 0.2 --sec 3")
        elif args.exit == "damp":
            gate("멘토 승인 — Damp 로 종료합니까? (행어 스트랩 하중 확인 준비)")
            link.led("damp")
            link.damp()
            call_text("Damp 확인 — 종료 절차 진행")
        else:
            while True:
                c = input("\n[종료] d=Damp(행어 하중·멘토 승인) / k=현재 자세 유지 > ").strip().lower()
                if c == "d":
                    gate("멘토 승인 — Damp 로 종료합니까? (행어 스트랩 하중 확인 준비)")
                    link.led("damp")
                    link.damp()
                    call_text("Damp 확인 — 종료 절차 진행")
                    break
                if c == "k":
                    link.release_arm()
                    print(f"  현재 자세 유지로 종료 — FSM {link.fsm_text()}")
                    break

    except KeyboardInterrupt:
        safe_exit(link, "Ctrl+C 중단", damp=(args.exit == "damp"))
    except AbortRun as e:
        safe_exit(link, str(e), damp=(args.exit == "damp"))
    except RealCommandError as e:
        safe_exit(link, str(e), damp=(args.exit == "damp"))
    except Exception as e:
        safe_exit(link, f"예외 {type(e).__name__}: {e}", damp=(args.exit == "damp"))
    finally:
        print(f"\n  소요 {time.monotonic() - t0:.0f}s — 관측 FSM 값을 기록하세요.")


if __name__ == "__main__":
    main()
