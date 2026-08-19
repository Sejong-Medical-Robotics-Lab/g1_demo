#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_common.py — G1 실기체 스크립트 공통 모듈.

왜 별도 모듈인가:
  LocoClient 의 Damp()/Start()/Squat2StandUp() 등은 내부적으로 SetFsmId() 를
  호출하지만 **반환값이 없다(None)**. 즉 로봇이 명령을 거부해도 파이썬 쪽에서는
  알 수 없다. 이 모듈은 SetFsmId()/SetVelocity() 를 '직접' 호출해 반환 코드를
  검사하는 얇은 래퍼를 제공한다.

  같은 이유로 Move() 대신 SetVelocity(vx, vy, omega, duration) 을 직접 쓴다.
  Move() 는 duration=1(초)로 고정이고, continous_move=True 는 864000초(10일)라
  데드맨 없이 쓰면 위험하다.

사용:
  from g1_common import G1Link, FSM, gate, banner, countdown
"""
import os
import sys
import time


# ── FSM ID (unitree_sdk2py/g1/loco/g1_loco_client.py 기준) ────────────
class FSM:
    ZERO_TORQUE = 0      # ZeroTorque()
    DAMP = 1             # Damp()
    SIT = 3              # Sit()
    START = 500          # Start() — 메인 컨트롤(균형 제어)
    LIE2STANDUP = 702    # Lie2StandUp()
    SQUAT_TOGGLE = 706   # Squat2StandUp() / StandUp2Squat() — 같은 ID(토글!)


FSM_NAME = {0: "ZeroTorque", 1: "Damp", 3: "Sit", 500: "Start(메인컨트롤)",
            702: "Lie2StandUp", 706: "Squat<->Stand"}

# 팔 액션 후 팔 제어 반납용 (action_map["release arm"])
RELEASE_ARM = "release arm"

# 상태별 LED 색 (R, G, B) — 데모에서 관객이 상태를 눈으로 알 수 있게 한다.
LED = {
    "damp":    (255, 0, 0),      # 빨강 — 힘 빠진 상태
    "standing": (255, 160, 0),   # 주황 — 기립 전이 중
    "balance": (0, 255, 0),      # 초록 — 균형 제어(안전하게 동작 가능)
    "arm":     (0, 120, 255),    # 파랑 — 상체 동작 중
    "walk":    (160, 0, 255),    # 보라 — 보행 중
    "error":   (255, 0, 0),      # 빨강 — 이상/중단
    "off":     (0, 0, 0),
}


def dds_init(domain, iface):
    """DDS 초기화 — CYCLONEDDS_URI 가 있으면 인터페이스 인자를 넘기지 않는다.

    Ubuntu 24.04 + cyclonedds 0.10.2 조합에서, SDK 가 인터페이스 이름을 받아
    만드는 설정 XML 에는 <Tracing>(/tmp/cdds.LOG) 블록이 들어 있는데 이걸
    처리하다 C 레벨에서 죽는다("buffer overflow detected"). 인터페이스 없이
    호출하는 경로는 그 블록이 없어 정상 동작하므로, 인터페이스 지정은
    CYCLONEDDS_URI 환경변수로 대신한다(g1_env.sh 가 설정).
    """
    import os
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize
    if os.environ.get("CYCLONEDDS_URI"):
        ChannelFactoryInitialize(domain)
    else:
        ChannelFactoryInitialize(domain, iface)


class AbortRun(Exception):
    """게이트 불통과·육안 확인 실패 — 즉시 Damp 수렴 경로."""


class RealCommandError(RuntimeError):
    """실기체 명령이 0이 아닌 코드로 거부됨."""


# ── 표시 유틸 ─────────────────────────────────────────────────────────
def banner(msg):
    line = "=" * 64
    print(f"\n{line}\n {msg}\n{line}")


def call_text(text):
    print(f'\n  >>> [콜] "{text}"')


def gate(prompt):
    """멘토/실행자 확인 게이트 — 'y' 만 진행."""
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
    if code not in (0, None):
        raise RealCommandError(
            f"{what} 거부/실패 (code={code}) — 현재 FSM 에서 허용되지 않는 전이이거나 "
            f"통신 문제. 멘토 확인.")


# ── 실기체 링크 ───────────────────────────────────────────────────────
class G1Link:
    """LocoClient + G1ArmActionClient 를 반환코드 검사와 함께 묶은 래퍼."""

    def __init__(self, iface, domain=0, timeout=10.0, with_arm=True,
                 with_audio=False, volume=None):
        try:
            from unitree_sdk2py.core.channel import ChannelFactoryInitialize
            from unitree_sdk2py.g1.loco.g1_loco_client import LocoClient
        except ImportError as e:
            sys.exit("unitree_sdk2py 를 찾을 수 없습니다 — venv 를 활성화했는지 확인하세요.\n"
                     "  cd ~/unitree_sdk2_python && source .venv/bin/activate\n"
                     f"(원인: {e})")
        if os.environ.get("CYCLONEDDS_URI"):
            ChannelFactoryInitialize(domain)      # 인터페이스는 URI 가 지정
        else:
            ChannelFactoryInitialize(domain, iface)
        self.loco = LocoClient()
        self.loco.SetTimeout(timeout)
        self.loco.Init()

        self.arm = None
        self.action_map = {}
        if with_arm:
            from unitree_sdk2py.g1.arm.g1_arm_action_client import (
                G1ArmActionClient, action_map)
            self.arm = G1ArmActionClient()
            self.arm.SetTimeout(timeout)
            self.arm.Init()
            self.action_map = dict(action_map)

        # 오디오는 '있으면 좋은' 기능이다 — 실패해도 제어 흐름을 막지 않는다.
        self.audio = None
        if with_audio:
            try:
                from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient
                self.audio = AudioClient()
                self.audio.SetTimeout(timeout)
                self.audio.Init()
                # SDK 버그 우회: TtsMaker 안의 `tts_index += tts_index` 는
                # 0 에서 시작하면 영원히 0 이다. 1 로 초기화하면 1,2,4,8… 로 증가한다.
                self.audio.tts_index = 1
                if volume is not None:
                    self.audio.SetVolume(int(volume))
            except Exception as e:
                print(f"  [오디오] 초기화 실패({e}) — 음성/LED 없이 계속 진행합니다.")
                self.audio = None

    # ── 음성·LED (실패해도 무시 — 제어를 막지 않는다) ────────────────
    def say(self, text, speaker_id=0):
        """TTS. 로봇이 말하는 동안 블로킹되지 않으므로 대기는 호출측 몫."""
        if self.audio is None:
            return
        try:
            self.audio.TtsMaker(text, speaker_id)
        except Exception:
            pass

    def led(self, state):
        """상태 이름('damp'/'balance'/…) 또는 (R,G,B) 튜플."""
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
        """LED 색과 음성을 함께 — 데모 진행 알림용."""
        if state:
            self.led(state)
        self.say(text)

    # ── 상태 조회 ────────────────────────────────────────────────────
    def fsm(self):
        """현재 FSM ID. 조회 실패 시 None (→ 육안 판정으로 대체)."""
        try:
            code, val = self.loco.GetFsmId()
            return val if code == 0 else None
        except Exception:
            return None

    def fsm_text(self):
        f = self.fsm()
        if f is None:
            return "조회 불가"
        return f"{f} ({FSM_NAME.get(f, '미상')})"

    # ── FSM 전이 (반환 코드 검사 O) ──────────────────────────────────
    def set_fsm(self, fsm_id, label=None):
        """SetFsmId 를 직접 호출해 반환 코드를 검사한다."""
        what = label or f"SetFsmId({fsm_id})"
        check_code(self.loco.SetFsmId(fsm_id), what)

    def damp(self):
        self.set_fsm(FSM.DAMP, "Damp")

    def wait_fsm(self, expect, settle=3.0, timeout=12.0, label=""):
        """기대 FSM 도달 대기. 도달하면 True, 시간초과면 False(육안 판정)."""
        t0 = time.monotonic()
        seen = None
        while time.monotonic() - t0 < timeout:
            el = time.monotonic() - t0
            seen = self.fsm()
            print(f"      … {label} 확인 {el:4.1f}s / FSM: "
                  f"{seen if seen is not None else '조회 불가'}   ",
                  end="\r", flush=True)
            if seen in expect and el >= settle:
                print()
                print(f"      FSM {seen} 확인 (기대값 {sorted(expect)})")
                return True
            time.sleep(0.5)
        print()
        print(f"      [주의] {timeout:.0f}초 내 기대 FSM {sorted(expect)} 미확인 "
              f"(마지막 관측: {seen}) — 펌웨어별 값 차이 가능, 육안으로 판정")
        return False

    # ── 팔 동작 ──────────────────────────────────────────────────────
    def wave(self, turn_flag=False):
        """LocoClient.WaveHand() — SetTaskId 경로. 균형 제어(FSM 500)에서만 동작."""
        self.loco.WaveHand(turn_flag)   # 반환값 없음 — 육안 확인이 판정

    def arm_action(self, name):
        if self.arm is None:
            raise RealCommandError("arm client 가 초기화되지 않음(with_arm=False)")
        aid = self.action_map.get(name)
        if aid is None:
            raise RealCommandError(f"action_map 에 없는 동작: '{name}'")
        check_code(self.arm.ExecuteAction(aid), f"ExecuteAction({name}={aid})")

    def release_arm(self):
        """팔 제어 반납(ID 99). 보행 전·시퀀스 종료 전에 반드시 호출."""
        if self.arm is None:
            return
        aid = self.action_map.get(RELEASE_ARM)
        if aid is not None:
            self.arm.ExecuteAction(aid)

    def action_list(self):
        try:
            code, data = self.arm.GetActionList()
            return data if code == 0 else None
        except Exception:
            return None

    # ── 보행 (SetVelocity 직접 호출 — 반환 코드 검사 O) ──────────────
    def set_velocity(self, vx, vy, vyaw, duration):
        """duration 초 동안만 유효한 속도 명령.

        루프가 죽거나 프로세스가 종료되면 duration 후 로봇이 스스로 멈춘다.
        이것이 이 프로젝트의 보행 데드맨 장치다.
        """
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


def safe_damp(link, reason):
    """어떤 경로로든 빠져나올 때의 마지막 수렴점."""
    banner(f"[안전] {reason} → 정지 + Damp 수렴 (행어가 하중을 받는다)")
    try:
        link.stop_move()
    except Exception:
        pass
    try:
        link.release_arm()
    except Exception:
        pass
    try:
        link.announce("비상 정지합니다", "error")
    except Exception:
        pass
    try:
        link.damp()
        print("      Damp 전송 완료 — 로봇·행어 상태를 눈으로 확인할 것")
    except Exception as e:
        print(f"      Damp 호출 실패({e}) — 멘토 리모컨(비상 Damp)으로 즉시 대응!")
