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
#     ("move",   (0.2,0,0),  3.0)   보행 — 2단계 단독 검증 후 --enable-walk 로만 허용
#     ("stop",   None,       2.0)   보행 정지 (move 뒤에는 반드시 stop)
#
#   대기시간 근거: 실기체 high-level 에는 시뮬의 ActionActive 같은 '완료 신호'가
#   없다(→ sim-to-real 관찰 항목). 시뮬 실측 시간 + 2~3초 여유로 잡는다.
#   전이(Damp·기립·균형)와 종료는 아래 프레임이 멘토 게이트와 함께 수행하므로
#   여기에는 상체 동작 행만 적는다. move/stop/standup/damp 행은 거부된다.
SEQUENCE = [
    ("action", "hands_up", 8.0),   # 양팔 들기
    ("hold",   None,       2.0)
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

# 전이 프레임 — FSM 번호가 다르면 '이 표만' 수정한다.
#   (라벨, 보낼 FSM ID, 기대 FSM 값 집합, 최소 안정화[s], 최대 대기[s])
#
#   ※ 왜 메서드명이 아니라 FSM ID 인가:
#     LocoClient.Damp()/Start()/Squat2StandUp() 은 내부에서 SetFsmId() 를 호출하지만
#     반환값이 없다(None). 그래서 check_code() 가 아무것도 검사하지 못한다.
#     SetFsmId() 를 직접 부르면 반환 코드를 받아 거부를 실제로 잡을 수 있다.
#   ※ 706 은 Squat2StandUp 과 StandUp2Squat 이 공유하는 ID(토글)다.
#     이미 서 있는 상태에서 다시 706 을 보내면 앉는다.
#   ※ 2026-07 master 기준: Damp=FSM1, Squat2StandUp=706(완료 후 4 보고 가능성),
#     Start=FSM500 (구버전: StandUp=4, Start=200). FSM 관측값이 다르면 육안 게이트가
#     최종 판정이며, 관측값을 운영가이드 FAQ 표에 기록해 다음 조에 인수인계한다.
#   실기체 관측으로 확정한 사슬: 0(전원 인가) → 1(Damp) → 4(Lock Stand) → 500/200
#   706 은 Damp 직후 거부된다(코드 0 을 반환해도 FSM 이 안 바뀜) — 기립은 4 다.
#   SDK 에 4 의 래퍼가 없어 SetFsmId(4) 로 직접 보낸다.
#   ★ 실기체 실측(2026-08) — 확정 사슬: 1 Damp → 4 Lock Stand → 501 레귤러
#     501 이어야 보행과 팔 액션이 모두 된다.
#     200 은 보행만 되고 팔 액션은 code=7404 로 거부된다.
#     500 은 이 기체에서 전이 자체가 안 된다.
#     SDK 에 501 래퍼가 없어 SetFsmId(501) 로 직접 보낸다.
TRANSITIONS = [
    ("Damp — 힘 빼기(알려진 안전 상태)", 1,   {1},   3.0,  8.0),
    ("Lock Stand — 잠금 기립(레디)",      4,   {4},   6.0, 15.0),
    ("레귤러 모드 진입 (보행 + 팔 액션)",   501, {501}, 5.0, 12.0),
]

# 보행 안전 상한 — ("move", (vx,vy,vyaw), sec) 행에 적용된다.
WALK_LIMIT_VX, WALK_LIMIT_VY, WALK_LIMIT_VYAW = 0.3, 0.2, 0.4
WALK_SEND_PERIOD = 0.2     # 재전송 주기 [s]
WALK_CMD_DURATION = 0.5    # 명령 유효 시간 [s] — 데드맨. SEND_PERIOD 보다 커야 한다.

LOG_PATH = "g1_session_log.csv"   # 교재 6.4 '한 줄 로그' 자동 기록

# --audio 일 때 쓰는 문구·LED. LED 색은 관객이 상태를 눈으로 알 수 있게 한다.
LED = {"damp": (255, 0, 0), "standing": (255, 160, 0), "balance": (0, 255, 0),
       "arm": (0, 120, 255), "walk": (160, 0, 255), "off": (0, 0, 0)}
# 상태별 LED 색. 음성 안내는 로봇 내장 음성이 담당한다 —
# G1 의 TtsMaker 는 한국어를 지원하지 않고 영어 발음도 부정확하다.
SPEECH = {1: (None, "damp"), 4: (None, "standing"),
          200: (None, "balance"), 500: (None, "balance"),
          501: (None, "balance")}


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


# SDK 의 RPC 에러 코드 (unitree_sdk2py/rpc/internal.py)
# 3104 는 전이 거부가 아니라 '응답 시간 초과'다.
RPC_ERR = {
    3102: "전송 실패", 3103: "API 미등록",
    3104: "응답 시간 초과 — 통신 문제(무선이면 유선 권장)",
    3105: "API 불일치", 3106: "데이터 오류", 3107: "lease 무효",
}

# arm 서비스가 반환하는 코드 (SDK 에 정의 없음 — 실기체 관측 기록)
ARM_ERR = {
    7404: "arm 서비스 거부 — 팔 제어권이 다른 창구(LocoClient WaveHand/ShakeHand)에 "
          "잡혀 있거나 현재 상태에서 불가. release 후 재시도할 것",
}


def check_code(code, what):
    """모든 명령의 반환 코드를 확인한다 — '거부당하는 코드를 쓰지 않는 것이 목표'(5.1)."""
    if code in (0, None):
        return
    if code in RPC_ERR:
        raise RealCommandError(f"{what} 실패 (code={code}) — {RPC_ERR[code]}")
    if code in ARM_ERR:
        raise RealCommandError(f"{what} 실패 (code={code}) — {ARM_ERR[code]}")
    raise RealCommandError(
        f"{what} 거부 (code={code}) — 현재 FSM에서 허용되지 않는 "
        f"전이(교재 2.4 상태 기계). 멘토 확인.")


# ── 실기체 클라이언트 래퍼 ─────────────────────────────────────────────
class RealG1:
    """unitree_sdk2py LocoClient + G1ArmActionClient 를 게이트·검사와 함께 묶은 것."""

    def __init__(self, iface, domain=0, timeout=10.0, with_audio=False,
                 volume=70):
        # SDK 임포트를 여기로 미룬다 — --dry-run 은 SDK 없이도 동작해야 한다.
        from unitree_sdk2py.core.channel import ChannelFactoryInitialize
        from unitree_sdk2py.g1.loco.g1_loco_client import LocoClient
        from unitree_sdk2py.g1.arm.g1_arm_action_client import (
            G1ArmActionClient, action_map)
        if os.environ.get("CYCLONEDDS_URI"):
            ChannelFactoryInitialize(domain)      # 인터페이스는 URI 가 지정
        else:
            ChannelFactoryInitialize(domain, iface)
        self.loco = LocoClient()
        self.loco.SetTimeout(timeout)
        self.loco.Init()
        self.arm = G1ArmActionClient()
        self.arm.SetTimeout(timeout)
        self.arm.Init()
        self.action_map = dict(action_map)

        # 오디오는 '있으면 좋은' 기능 — 실패해도 제어 흐름을 막지 않는다.
        self.audio = None
        if with_audio:
            try:
                from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient
                self.audio = AudioClient()
                self.audio.SetTimeout(timeout)
                self.audio.Init()
                # SDK 버그 우회: TtsMaker 의 `tts_index += tts_index` 는 0 에서
                # 시작하면 영원히 0 이다. 1 로 두면 1,2,4,8… 로 증가한다.
                self.audio.tts_index = 1
                self.audio.SetVolume(int(volume))
                self.tts_enabled = False   # 우리 TTS 는 쓰지 않는다(한국어 미지원)
            except Exception as e:
                print(f"  [오디오] 초기화 실패({e}) — 음성/LED 없이 진행합니다.")
                self.audio = None

    def say(self, text):
        """기본 비활성 — 안내는 로봇 내장 음성이 담당한다."""
        if self.audio is None or not getattr(self, "tts_enabled", False):
            return
        try:
            self.audio.TtsMaker(text, 0)
        except Exception:
            pass

    def led(self, state):
        if self.audio is None:
            return
        rgb = LED.get(state) if isinstance(state, str) else state
        if rgb is None:
            return
        try:
            self.audio.LedControl(int(rgb[0]), int(rgb[1]), int(rgb[2]))
        except Exception:
            pass

    def announce(self, text, state=None):
        if state:
            self.led(state)
        self.say(text)

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
        self.set_fsm(1, "Damp")

    def set_fsm(self, fsm_id, label=None):
        """SetFsmId 를 직접 호출해 반환 코드를 검사한다.

        Damp()/Start()/Squat2StandUp() 래퍼는 반환값이 없어(None) 거부를 놓친다.
        """
        check_code(self.loco.SetFsmId(fsm_id), label or f"SetFsmId({fsm_id})")

    def set_velocity(self, vx, vy, vyaw, duration):
        """duration 초 동안만 유효한 속도 명령 — 루프가 죽으면 스스로 멈춘다."""
        check_code(self.loco.SetVelocity(vx, vy, vyaw, duration),
                   f"SetVelocity({vx:.2f},{vy:.2f},{vyaw:.2f},{duration:.2f})")

    def stop_move(self):
        """정지 — 실패 가능성을 감안해 3회 반복 전송."""
        for _ in range(3):
            try:
                self.loco.SetVelocity(0.0, 0.0, 0.0, 0.5)
            except Exception:
                pass
            time.sleep(0.05)

    def release_arm(self):
        """팔 제어 반납(action_map["release arm"]=99).


        보행 전·시퀀스 종료 전에 반드시 호출한다. 팔 액션이 팔을 잡고 있으면
        보행 중 상체 보상이 방해받는다.
        """
        if self.skip_release:
            return
        aid = self.action_map.get("release arm")
        if aid is not None:
            try:
                self.arm.ExecuteAction(aid)
            except Exception:
                pass

    def wave(self):
        check_code(self.loco.WaveHand(), "WaveHand")

    skip_release = False    # --no-release 로 켜면 해제 호출을 하지 않는다

    def release_loco_arm(self):
        """LocoClient 쪽 팔 태스크 해제.

        WaveHand()/ShakeHand() 는 LocoClient.SetTaskId 로 팔을 잡는다.
        이 태스크를 쥔 채로 G1ArmActionClient.ExecuteAction 을 부르면
        arm 서비스가 거부한다(실기체에서 code=7404 관측).
        두 창구를 섞을 때는 반드시 이 해제를 사이에 넣는다.
        """
        if self.skip_release:
            return
        try:
            self.loco.SetTaskId(99)     # 99 = release (추정값 — 미검증)
        except Exception:
            pass

    def arm_action(self, name):
        aid = self.action_map.get(name)
        if aid is None:
            raise RealCommandError(f"action_map 에 없는 동작: '{name}' — --list-actions 로 확인")
        check_code(self.arm.ExecuteAction(aid), f"ExecuteAction({name}={aid})")


# ── 시퀀스 해석·검증 ───────────────────────────────────────────────────
def clamp(v, lim, name, problems, row):
    if abs(v) > lim:
        problems.append(f"{row}행: {name} {v:+.2f} 가 안전 상한 {lim} 초과")
        return lim if v > 0 else -lim
    return v


def resolve_sequence(seq, enable_walk=False):
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
        elif kind == "move":
            if not enable_walk:
                problems.append(f"{i}행: 보행 행은 기본 비활성 — 2단계(g1_walk_test.py)"
                                " 단독 검증을 마친 뒤 --enable-walk 로 실행")
                continue
            try:
                vx, vy, vyaw = (float(v) for v in arg)
            except Exception:
                problems.append(f"{i}행: move 인자는 (vx, vy, vyaw) 튜플이어야 함")
                continue
            vx = clamp(vx, WALK_LIMIT_VX, "vx", problems, i)
            vy = clamp(vy, WALK_LIMIT_VY, "vy", problems, i)
            vyaw = clamp(vyaw, WALK_LIMIT_VYAW, "vyaw", problems, i)
            plan.append((i, "move", f"보행 vx={vx:+.2f} vy={vy:+.2f} vyaw={vyaw:+.2f}",
                         (vx, vy, vyaw), float(wait)))
        elif kind == "stop":
            if not enable_walk:
                problems.append(f"{i}행: 'stop' 은 --enable-walk 에서만 유효")
                continue
            plan.append((i, "stop", "보행 정지", None, float(wait)))
        elif kind in ("standup", "damp"):
            problems.append(f"{i}행: '{kind}' 는 학생 SEQUENCE 에서 금지 — "
                            "전이는 프레임 소관")
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
def do_transition(robot, label, fsm_id, expect, settle, timeout):
    banner(f"전이: {label}  (SetFsmId {fsm_id})")
    gate(f"멘토 승인 — '{label}' 실행해도 됩니까?")
    text, color = SPEECH.get(fsm_id, (None, None))
    if color:
        robot.led(color)
    if text:
        robot.say(text)
    manual = False
    try:
        robot.set_fsm(fsm_id, label)
    except RealCommandError as e:
        if not getattr(e, "timeout", False):
            raise
        print(f"\n  {e}")
        print("\n  [수동 확인] 통신으로 확인하지 못했습니다 — 응답 시간 초과.")
        ans = input(f"           로봇이 실제로 '{label}' 상태입니까? "
                    "(y=작업자 확인으로 진행 / 그 외=중단) > ").strip().lower()
        if ans != "y":
            raise AbortRun(f"{label} — 통신 확인 실패, 작업자도 확인 못함")
        manual = True
        print("           → 작업자 육안 확인으로 진행 (기록에 남김)")

    call_text(f"{label} — SetFsmId({fsm_id}) 전송"
              + ("  [작업자 육안 확인]" if manual else ""))
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


def safe_exit(robot, reason, damp=False):
    """빠져나올 때의 수렴점.

    damp=False (기본): 이동 정지 + 팔 반납만 하고 **현재 자세를 유지**한다.
      서 있는 로봇에 Damp 를 보내면 힘이 빠져 주저앉는다. 한 동작이 거부됐다고
      전체를 무너뜨릴 이유는 없고, 원인을 확인한 뒤 이어서 재시도하는 편이 낫다.
    damp=True: 명시적으로 Damp 까지 보낸다(--exit damp).
    """
    banner(f"[안전] {reason} → "
           + ("Damp 수렴 (행어가 하중을 받는다)" if damp
              else "이동 정지 · 팔 반납 · 현재 자세 유지"))
    try:
        robot.stop_move()
        robot.release_arm()
    except Exception:
        pass
    if not damp:
        try:
            robot.led("error")
        except Exception:
            pass
        try:
            f = robot.fsm()
            print(f"      현재 FSM: {f}")
        except Exception:
            print("      현재 FSM: 조회 불가(통신 문제)")
        print("      로봇은 자세를 유지 중이다 — 필요하면 리모컨으로 Damp.")
        return
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
    ap.add_argument("--no-release", action="store_true",
                    help="팔 제어권 해제 호출을 전혀 하지 않음 — 해제 자체가 "
                         "7404 의 원인인지 가릴 때 사용")
    ap.add_argument("--exit", choices=["keep", "damp"], default="keep",
                    help="이상 종료 시: keep=자세 유지(기본) / damp=Damp 로 내림")
    ap.add_argument("--audio", action="store_true",
                    help="LED 색으로 상태 표시 (음성은 로봇 내장 음성이 담당)")
    ap.add_argument("--volume", type=int, default=70, help="--audio 볼륨 0~100")
    ap.add_argument("--enable-walk", action="store_true",
                    help="SEQUENCE 의 move/stop 행 허용 — 2단계 단독 검증 완료 후에만")
    ap.add_argument("--dry-run", action="store_true", help="설계 리뷰만(로봇·SDK 불필요)")
    ap.add_argument("--list-actions", action="store_true",
                    help="SDK action_map + 실기체 GetActionList 대조 출력 후 종료")
    args = ap.parse_args()

    banner("과제 2 — 상체 모션 시퀀스 (실기체 · 행어 · 멘토 확인 하)")
    plan, problems = resolve_sequence(SEQUENCE, enable_walk=args.enable_walk)
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
    if args.enable_walk:
        gate("[보행 포함] 진행 방향에 사람·장애물이 없고 공간이 확보되었습니까?")

    try:
        robot = RealG1(args.iface, args.domain, with_audio=args.audio,
                       volume=args.volume)
        robot.skip_release = args.no_release
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
            for label, fsm_id, expect, settle, timeout in TRANSITIONS:
                do_transition(robot, label, fsm_id, expect, settle, timeout)
                if label.startswith("Damp"):
                    call_text("Damp 확인 — 상태 정상 콜 요청")           # SOP ③
                    gate("모니터링 담당의 '상태 정상' 콜을 받았습니까?")
        call_text("기립 완료 — 모션 실행합니다")                           # SOP ④

        for i, how, label, real, wait in plan:
            print(f"\n  [{i}/{len(plan)}] {label}")
            if how == "hold":
                countdown(wait, label)
            elif how == "loco_wave":
                robot.led("arm")
                robot.wave()
                countdown(wait, label)
                robot.release_loco_arm()     # 다음 arm 액션을 위해 창구 비우기
                time.sleep(1.0)
            elif how == "arm":
                robot.led("arm")
                robot.release_loco_arm()     # loco 쪽이 팔을 쥐고 있으면 7404
                time.sleep(0.5)
                robot.arm_action(real)
                countdown(wait, label)
                robot.release_arm()          # 팔 제어 반납 — 다음 동작/보행을 위해
                print("      release arm 전송")
            elif how == "move":
                robot.led("walk")
                robot.release_arm()          # 보행 전 팔 반납
                vx, vy, vyaw = real
                t_end = time.monotonic() + wait
                while time.monotonic() < t_end:
                    robot.set_velocity(vx, vy, vyaw, WALK_CMD_DURATION)
                    remain = t_end - time.monotonic()
                    print(f"      … 보행 남은 {max(remain, 0):4.1f}s   ",
                          end="\r", flush=True)
                    time.sleep(min(WALK_SEND_PERIOD, max(remain, 0.01)))
                print(" " * 60, end="\r")
                robot.stop_move()            # 구간 끝에서 항상 정지
            elif how == "stop":
                robot.led("balance")
                robot.stop_move()
                countdown(wait, label)
            f = robot.fsm()
            if f is not None:
                print(f"      현재 FSM: {f}")

        robot.stop_move()
        robot.release_arm()
        robot.led("balance")
        call_text("시퀀스 완료")
        result = f"정상 완료 ({len(plan)}행)"

        # 종료 선택 — 교재 5장 '끝도 알려진 상태로' + SOP ⑥
        while True:
            c = input("\n[종료] d=Damp(행어가 하중·멘토 승인 필요) / k=기립 유지"
                      "(다음 실행자 대기) > ").strip().lower()
            if c == "d":
                gate("멘토 승인 — Damp 로 종료합니까? (행어 스트랩 하중 확인 준비)")
                robot.led("damp")
                robot.damp()
                call_text("Damp 확인 — 종료 절차 진행")
                break
            if c == "k":
                print("  기립(균형) 유지 상태로 종료 — 다음 실행자에게 인계.")
                break

    except KeyboardInterrupt:
        result, abnormal = "중단: Ctrl+C", "유(중단)"
        safe_exit(robot, "Ctrl+C 중단", damp=(args.exit == "damp"))
    except AbortRun as e:
        result, abnormal = f"중단: {e}", "유(게이트)"
        safe_exit(robot, str(e), damp=(args.exit == "damp"))
    except RealCommandError as e:
        result, abnormal = f"거부/실패: {e}", "유(거부)"
        safe_exit(robot, str(e), damp=(args.exit == "damp"))
    except Exception as e:
        result, abnormal = f"예외: {type(e).__name__}: {e}", "유(예외)"
        safe_exit(robot, f"예외 {type(e).__name__}", damp=(args.exit == "damp"))
    finally:
        try:
            append_log(args.operator, plan, result, abnormal, time.monotonic() - t_start)
        except Exception:
            pass
        print("\n  종료 — 예약표·영상·bag 기록 여부를 확인하세요 (교재 6.4).")


if __name__ == "__main__":
    main()
