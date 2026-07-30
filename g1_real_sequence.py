#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_real_sequence.py — 과제 2 실기체 실행기 (행어 위 · 멘토 확인 하).

교재4 대응 : 5장(Damp 원칙·상태 전이·실행 전 설명 가능) / 6장 SOP ③~④·6.4 한 줄 로그
             / 7장 과제 2(상체 모션 시퀀스).
위치       : g1-edu 저장소와 '별도 폴더'(예: ~/g1_real/)에 둔다 — docs/real_robot.md 원칙.
             시뮬 검증은 g1-edu(03_sequence_template / mission4_sequence)에서 마치고,
             그 설계 시트의 '상체 동작 행'만 아래 SEQUENCE 로 옮긴다.
전제 조건  : unitree_sdk2_python 설치, 실행 PC 유선 192.168.123.x 대역.
             행어 거치 + 멘토 리모컨(비상 Damp) 확인 없이는 절대 실행하지 않는다.

사용 예:
  python3 g1_real_sequence.py --dry-run                       # 설계 리뷰(로봇 불필요)
  python3 g1_real_sequence.py --iface enp2s0 --list-actions   # 실기체 동작 목록 대조
  python3 g1_real_sequence.py --iface enp2s0 --operator 김OO   # 본 실행 (전이 포함)
  python3 g1_real_sequence.py --iface enp2s0 --arm-only       # 멘토가 이미 기립·균형을
                                                              # 잡아 둔 상태에서 팔 동작만

이 스크립트에는 보행 명령(Move)이 없다 — 보행은 SOP ⑤에 따라 멘토 주도로만 한다.
"""
import argparse
import csv
import datetime as _dt
import os
import sys
import time

# ══════════════════════════════════════════════════════════════════════
# [학생 편집 구역] — 설계 시트(교재 7.3)의 '상체 동작 행'을 옮기는 곳
#
#   행 형식: (동작종류, 인자, 다음 단계 전 대기시간[s])   ← 시뮬 템플릿과 동일
#     ("action", "wave",     8.0)   시뮬 레지스트리 이름 → 아래 REAL_ACTIONS 로 매핑
#     ("action", "hands up", 8.0)   실기체 팔 액션 이름 직접 지정도 가능(멘토 승인 필요)
#     ("hold",   None,       2.0)   동작 없이 관찰 대기
#
#   대기시간 근거: 실기체 high-level 에는 시뮬의 ActionActive 같은 '완료 신호'가
#   없다(→ sim-to-real 관찰 항목). 시뮬 실측 시간 + 2~3초 여유로 잡는다.
#   전이(Damp·기립·균형)와 종료는 아래 프레임이 멘토 게이트와 함께 수행하므로
#   여기에는 상체 동작 행만 적는다. move/stop/standup/damp 행은 거부된다.
SEQUENCE = [
    ("action", "wave",     8.0),   # 손 흔들기 (시뮬 검증 완료분)
    ("hold",   None,       2.0),   # 안정화 관찰 — 하체·허리 보상 보기(교재 2.2)
    ("action", "hands_up", 8.0),   # 양팔 들기
]
# ══════════════════════════════════════════════════════════════════════

# 시뮬(g1-edu 레지스트리) 이름 → 실기체 호출 매핑.
#   ("loco_wave", None)  : LocoClient.WaveHand() — 균형 유지하며 손 흔들기
#   ("arm", "<이름>")    : G1ArmActionClient action_map 의 액션
#   None                 : 실기체 미지원(시뮬 전용) — 설계 단계에서 제외할 것
REAL_ACTIONS = {
    "wave":     ("loco_wave", None),
    "hands_up": ("arm", "hands up"),
    "bow":      None,   # 실기체 액션 목록에 대응 동작 없음(사전 검증에서 재확인)
}

# 전이 프레임 — SDK 버전에 따라 메서드명·FSM 번호가 다르면 '이 표만' 수정한다.
#   (라벨, 시도할 메서드 후보(앞선 것 우선), 기대 FSM 값 집합, 최소 안정화[s], 최대 대기[s])
#   ※ 2026-07 master 기준: Damp=FSM1, Squat2StandUp=706(완료 후 4 보고 가능성),
#     Start=FSM500 (구버전: StandUp=4, Start=200). FSM 관측값이 다르면 육안 게이트가
#     최종 판정이며, 관측값을 운영가이드 FAQ 표에 기록해 다음 조에 인수인계한다.
TRANSITIONS = [
    ("Damp — 힘 빼기(알려진 안전 상태)", ("Damp",),                    {1},           3.0, 8.0),
    ("기립 전이(위치잠금 기립)",         ("Squat2StandUp", "StandUp"), {4, 706},      6.0, 15.0),
    ("메인 컨트롤(균형 제어) 진입",       ("Start",),                   {500, 200},    5.0, 12.0),
]

LOG_PATH = "g1_session_log.csv"   # 교재 6.4 '한 줄 로그' 자동 기록


# ── 공통 유틸 ──────────────────────────────────────────────────────────
class AbortRun(Exception):
    """게이트 불통과·육안 확인 실패 등 — 즉시 Damp 수렴 경로."""


class RealCommandError(RuntimeError):
    """실기체 명령이 0이 아닌 코드로 거부됨 — 시뮬 CommandRejected 의 실기체판."""


def banner(msg):
    line = "=" * 64
    print(f"\n{line}\n {msg}\n{line}")


def call_text(text):
    print(f'\n  >>> [콜] "{text}"')


def gate(prompt):
    """멘토/실행자 확인 게이트 — 'y' 만 진행, 그 외는 전부 중단(→Damp)."""
    ans = input(f"[게이트] {prompt}  (y=진행 / 그 외=중단) > ").strip().lower()
    if ans != "y":
        raise AbortRun(f"게이트 불통과: {prompt}")


def countdown(sec, label):
    end = time.monotonic() + sec
    while True:
        remain = end - time.monotonic()
        if remain <= 0:
            break
        print(f"      … {label} 대기 {remain:4.1f}s", end="\r", flush=True)
        time.sleep(min(0.2, remain))
    print(" " * 60, end="\r")


def check_code(code, what):
    """모든 명령의 반환 코드를 확인한다 — '거부당하는 코드를 쓰지 않는 것이 목표'(5.1)."""
    if code not in (0, None):
        raise RealCommandError(
            f"{what} 거부/실패 (code={code}) — 현재 FSM에서 허용되지 않는 "
            f"전이(교재 2.4 상태 기계)이거나 통신 문제. 멘토 확인.")


# ── 실기체 클라이언트 래퍼 ─────────────────────────────────────────────
class RealG1:
    """unitree_sdk2py LocoClient + G1ArmActionClient 를 게이트·검사와 함께 묶은 것."""

    def __init__(self, iface, domain=0, timeout=10.0):
        # SDK 임포트를 여기로 미룬다 — --dry-run 은 SDK 없이도 동작해야 한다.
        from unitree_sdk2py.core.channel import ChannelFactoryInitialize
        from unitree_sdk2py.g1.loco.g1_loco_client import LocoClient
        from unitree_sdk2py.g1.arm.g1_arm_action_client import (
            G1ArmActionClient, action_map)
        ChannelFactoryInitialize(domain, iface)
        self.loco = LocoClient()
        self.loco.SetTimeout(timeout)
        self.loco.Init()
        self.arm = G1ArmActionClient()
        self.arm.SetTimeout(timeout)
        self.arm.Init()
        self.action_map = dict(action_map)

    # 상태 조회 — GetFsmId 는 (code, value) 를 반환한다(2026-07 master 확인).
    def fsm(self):
        try:
            ret = self.loco.GetFsmId()
            if isinstance(ret, tuple):
                code, val = ret
                return val if code == 0 else None
            return ret
        except Exception:
            return None   # 구버전/미지원 — 육안 확인으로 대체

    def robot_action_list(self):
        """실기체가 실제로 보고하는 액션 목록(GetActionList) — 사전 검증용."""
        try:
            code, data = self.arm.GetActionList()
            return data if code == 0 else None
        except Exception:
            return None

    # 개별 호출 (반환 코드 검사 포함)
    def damp(self):
        check_code(self.loco.Damp(), "Damp")

    def run_method(self, names):
        for n in names:
            fn = getattr(self.loco, n, None)
            if fn is not None:
                check_code(fn(), n)
                return n
        raise RealCommandError(f"이 SDK 버전에 {names} 메서드가 없음 — TRANSITIONS 표 수정 필요")

    def wave(self):
        check_code(self.loco.WaveHand(), "WaveHand")

    def arm_action(self, name):
        aid = self.action_map.get(name)
        if aid is None:
            raise RealCommandError(f"action_map 에 없는 동작: '{name}' — --list-actions 로 확인")
        check_code(self.arm.ExecuteAction(aid), f"ExecuteAction({name}={aid})")


# ── 시퀀스 해석·검증 ───────────────────────────────────────────────────
def resolve_sequence(seq):
    """SEQUENCE 를 실행 계획으로 변환. 금지 행·미지원 동작은 여기서 걸러진다."""
    plan, problems = [], []
    for i, row in enumerate(seq, 1):
        try:
            kind, arg, wait = row
        except Exception:
            problems.append(f"{i}행: 형식 오류 — (동작, 인자, 대기초) 3열이어야 함")
            continue
        if kind == "hold":
            plan.append((i, "hold", "(관찰 대기)", None, float(wait)))
        elif kind == "action":
            if arg in REAL_ACTIONS:
                mapping = REAL_ACTIONS[arg]
                if mapping is None:
                    problems.append(f"{i}행: '{arg}' 는 실기체 미지원(시뮬 전용) — 행 제거 또는 대체")
                else:
                    how, real = mapping
                    label = f"{arg} → " + ("WaveHand(loco)" if how == "loco_wave"
                                           else f"팔 액션 '{real}'")
                    plan.append((i, how, label, real, float(wait)))
            else:
                # 실기체 팔 액션 이름을 직접 지정한 경우(시뮬 미검증 → 멘토 승인 대상)
                plan.append((i, "arm", f"팔 액션 '{arg}' (시뮬 미검증·멘토 승인 필요)",
                             arg, float(wait)))
        elif kind in ("move", "stop", "standup", "damp"):
            problems.append(f"{i}행: '{kind}' 는 학생 SEQUENCE 에서 금지 — "
                            "전이는 프레임 소관, 보행은 멘토 주도(SOP ⑤)")
        else:
            problems.append(f"{i}행: 알 수 없는 동작종류 '{kind}'")
    return plan, problems


def print_plan(plan):
    print("\n  실행 계획 (설계 시트 ↔ 1:1 대조용)")
    print("  ┌────┬──────────────────────────────────────────────┬────────┐")
    print("  │ 행 │ 동작                                         │ 대기 s │")
    print("  ├────┼──────────────────────────────────────────────┼────────┤")
    for i, how, label, real, wait in plan:
        print(f"  │ {i:>2d} │ {label:<44s} │ {wait:>5.1f}  │")
    print("  └────┴──────────────────────────────────────────────┴────────┘")
    print("  전이 경로(프레임 소관): Damp → 기립(위치잠금) → 균형 제어 →"
          " [위 동작들] → 종료 선택(Damp/기립 유지)")


# ── 전이 실행 ──────────────────────────────────────────────────────────
def do_transition(robot, label, methods, expect, settle, timeout):
    banner(f"전이: {label}")
    gate(f"멘토 승인 — '{label}' 실행해도 됩니까?")
    used = robot.run_method(methods)
    call_text(f"{label} — {used} 전송")
    t0 = time.monotonic()
    seen = None
    while time.monotonic() - t0 < timeout:
        el = time.monotonic() - t0
        seen = robot.fsm()
        shown = seen if seen is not None else "조회 불가(구버전)"
        print(f"      … 전이 확인 {el:4.1f}s / FSM: {shown}   ", end="\r", flush=True)
        if seen in expect and el >= settle:
            print()
            print(f"      FSM {seen} 확인 (기대값 {sorted(expect)})")
            break
        time.sleep(0.5)
    else:
        print()
        print(f"      [주의] {timeout:.0f}초 내 기대 FSM {sorted(expect)} 미확인"
              f" (마지막 관측: {seen}) — 펌웨어별 값 차이일 수 있음, 육안으로 판정")
    ans = input(f'[확인] "{label}" 완료를 육안으로 확인했습니까? '
                f"(y=계속 / x=즉시 Damp) > ").strip().lower()
    if ans != "y":
        raise AbortRun(f"{label} 육안 확인 실패")


def safe_damp(robot, reason):
    banner(f"[안전] {reason} → Damp 수렴 (행어가 하중을 받는다)")
    try:
        robot.damp()
        print("      Damp 전송 완료 — 로봇·행어 상태를 눈으로 확인할 것")
    except Exception as e:   # Damp 조차 실패하면 사람이 우선한다(교재 2.4)
        print(f"      Damp 호출 실패({e}) — 멘토 리모컨(비상 Damp)으로 즉시 대응!")


# ── 한 줄 로그 (교재 6.4) ─────────────────────────────────────────────
def append_log(operator, plan, result, abnormal, dur):
    new = not os.path.exists(LOG_PATH)
    with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["시각", "스크립트/동작", "실행자", "결과 한 줄", "이상 콜", "소요(s)"])
        acts = "→".join(str(p[2]).split(" → ")[0].split(" (")[0] for p in plan) or "-"
        w.writerow([_dt.datetime.now().strftime("%m/%d %H:%M:%S"),
                    f"g1_real_sequence [{acts}]", operator, result, abnormal, f"{dur:.0f}"])
    print(f"\n  한 줄 로그 기록 → {LOG_PATH}")


# ── 메인 ──────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="과제 2 실기체 실행기 (행어·멘토 확인 하)")
    ap.add_argument("--iface", help="로봇이 연결된 네트워크 인터페이스 (예: enp2s0)")
    ap.add_argument("--domain", type=int, default=0, help="DDS domain id (실기체 기본 0)")
    ap.add_argument("--operator", default="-", help="실행자 이름(한 줄 로그용)")
    ap.add_argument("--arm-only", action="store_true",
                    help="전이 생략 — 멘토가 조이스틱으로 이미 균형 제어까지 올린 상태에서 팔 동작만")
    ap.add_argument("--dry-run", action="store_true", help="설계 리뷰만(로봇·SDK 불필요)")
    ap.add_argument("--list-actions", action="store_true",
                    help="SDK action_map + 실기체 GetActionList 대조 출력 후 종료")
    args = ap.parse_args()

    banner("과제 2 — 상체 모션 시퀀스 (실기체 · 행어 · 멘토 확인 하)")
    plan, problems = resolve_sequence(SEQUENCE)
    print_plan(plan)
    if problems:
        print("\n  [설계 문제 — 실행 불가]")
        for p in problems:
            print("   ·", p)
        sys.exit(1)

    if args.dry_run:
        print("\n  --dry-run: 여기까지가 코드 리뷰(실행 전 설명 가능, 교재 7.3 ③)용 출력입니다.")
        return

    if not args.iface:
        sys.exit("--iface 가 필요합니다 (예: --iface enp2s0). 설계 리뷰만 하려면 --dry-run.")

    # ── 실행 전 게이트 3종 (SOP ①~②·리모컨) — 순서 고정 ──
    gate("SOP ① 5단계 체크(예약표·동석·비상정지·공간·코드 설명) 완료했습니까?")
    gate("SOP ② 행어 거치 확인 콜(멘토) 완료했습니까? — 발은 지면, 하중은 다리, 스트랩은 느슨")
    gate("멘토가 리모컨(비상 Damp) 소지 중이고, 즉시 조작 가능한 위치입니까?")
    gate("모니터링 담당이 g1_real_monitor.py watch 가동 중입니까? (교재 6.3)")

    try:
        robot = RealG1(args.iface, args.domain)
    except ImportError as e:
        sys.exit("unitree_sdk2py 를 찾을 수 없습니다 — 운영가이드 0장 설치 절차 참조.\n"
                 f"(원인: {e})")

    if args.list_actions:
        print("\n  SDK action_map:")
        for k, v in sorted(robot.action_map.items(), key=lambda kv: kv[1]):
            print(f"    {v:>3d}  {k}")
        print("\n  실기체 GetActionList 응답:")
        print("   ", robot.robot_action_list() or "(조회 실패 — 균형 제어 상태에서 재시도)")
        return

    t_start = time.monotonic()
    result, abnormal = "미기입", "무"
    try:
        if args.arm_only:
            f = robot.fsm()
            print(f"\n  --arm-only 모드: 현재 FSM = {f if f is not None else '조회 불가'}")
            gate("멘토 확인 — 로봇이 이미 '균형 제어(메인 컨트롤)' 상태입니까?")
        else:
            for label, methods, expect, settle, timeout in TRANSITIONS:
                do_transition(robot, label, methods, expect, settle, timeout)
                if label.startswith("Damp"):
                    call_text("Damp 확인 — 상태 정상 콜 요청")           # SOP ③
                    gate("모니터링 담당의 '상태 정상' 콜을 받았습니까?")
        call_text("기립 완료 — 모션 실행합니다")                           # SOP ④

        for i, how, label, real, wait in plan:
            print(f"\n  [{i}/{len(plan)}] {label}")
            if how == "hold":
                pass
            elif how == "loco_wave":
                robot.wave()
            elif how == "arm":
                robot.arm_action(real)
            countdown(wait, label)
            f = robot.fsm()
            if f is not None:
                print(f"      현재 FSM: {f}")

        call_text("시퀀스 완료")
        result = f"정상 완료 ({len(plan)}행)"

        # 종료 선택 — 교재 5장 '끝도 알려진 상태로' + SOP ⑥
        while True:
            c = input("\n[종료] d=Damp(행어가 하중·멘토 승인 필요) / k=기립 유지"
                      "(다음 실행자 대기) > ").strip().lower()
            if c == "d":
                gate("멘토 승인 — Damp 로 종료합니까? (행어 스트랩 하중 확인 준비)")
                robot.damp()
                call_text("Damp 확인 — 종료 절차 진행")
                break
            if c == "k":
                print("  기립(균형) 유지 상태로 종료 — 다음 실행자에게 인계.")
                break

    except KeyboardInterrupt:
        result, abnormal = "중단: Ctrl+C", "유(중단)"
        safe_damp(robot, "Ctrl+C 중단")
    except AbortRun as e:
        result, abnormal = f"중단: {e}", "유(게이트)"
        safe_damp(robot, str(e))
    except RealCommandError as e:
        result, abnormal = f"거부/실패: {e}", "유(거부)"
        safe_damp(robot, str(e))
    except Exception as e:
        result, abnormal = f"예외: {type(e).__name__}: {e}", "유(예외)"
        safe_damp(robot, f"예외 {type(e).__name__}")
    finally:
        try:
            append_log(args.operator, plan, result, abnormal, time.monotonic() - t_start)
        except Exception:
            pass
        print("\n  종료 — 예약표·영상·bag 기록 여부를 확인하세요 (교재 6.4).")


if __name__ == "__main__":
    main()
