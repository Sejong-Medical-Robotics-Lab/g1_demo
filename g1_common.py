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
    ZERO_TORQUE = 0      # ZeroTorque() — 전원 인가 직후의 기본 상태(관측용, 보내지 않는다)
    DAMP = 1             # Damp()
    SQUAT = 2            # 래퍼 없음
    SIT = 3              # Sit()
    LOCK_STAND = 4       # ★ 잠금 기립 — SDK 에 래퍼가 없어 SetFsmId(4) 로 직접 보낸다
    MAIN_CONTROL = 200   # 래퍼 없음 — Start() 가 안 통할 때의 대안
    START = 500          # Start() — 메인 컨트롤(균형 제어)
    LIE2STANDUP = 702    # Lie2StandUp()
    SQUAT_TOGGLE = 706   # Squat2StandUp() / StandUp2Squat() — 같은 ID(토글!)
                         # Damp 직후에는 거부된다. 반드시 LOCK_STAND 를 거친 뒤에 쓴다.


FSM_NAME = {0: "ZeroTorque", 1: "Damp", 2: "Squat", 3: "Sit", 4: "LockStand(잠금기립)",
            200: "MainControl", 500: "Start(메인컨트롤)",
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


# SDK 의 RPC 에러 코드 (unitree_sdk2py/rpc/internal.py)
# 3104 는 '전이 거부'가 아니라 '응답 시간 초과'다 — 통신 문제와 상태 거부를
# 구분하지 못하면 엉뚱한 곳을 고치게 된다.
RPC_ERR = {
    3102: "전송 실패(RPC_ERR_CLIENT_SEND)",
    3103: "API 미등록(RPC_ERR_CLIENT_API_NOT_REG)",
    3104: "응답 시간 초과(RPC_ERR_CLIENT_API_TIMEOUT) — 통신 문제",
    3105: "API 불일치(RPC_ERR_CLIENT_API_NOT_MATCH)",
    3106: "데이터 오류(RPC_ERR_CLIENT_API_DATA)",
    3107: "lease 무효(RPC_ERR_CLIENT_LEASE_INVALID)",
}
RPC_TIMEOUT = 3104


class AbortRun(Exception):
    """게이트 불통과·육안 확인 실패 — 즉시 Damp 수렴 경로."""


class RealCommandError(RuntimeError):
    """실기체 명령이 0이 아닌 코드로 거부됨.

    timeout=True 이면 '거부'가 아니라 '응답을 못 받았다'는 뜻이다.
    이 경우 명령 자체는 로봇에 도착했을 수 있으므로, 작업자의 육안 확인으로
    진행 여부를 판단할 여지를 남긴다.
    """

    def __init__(self, msg, timeout=False):
        super().__init__(msg)
        self.timeout = timeout


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


def manual_confirm(label, detail=""):
    """통신으로 확인이 안 될 때, 작업자의 육안 판정을 근거로 삼는다.

    로봇이 실제로는 명령을 받아 상태가 바뀌었는데 응답만 유실되는 일이 잦다.
    그때 스크립트가 무조건 중단해 버리면 눈앞의 사실과 어긋난다.
    판단 주체를 사람에게 넘기되, 그 사실을 로그에 남긴다.
    """
    print(f"\n  [수동 확인] 통신으로 확인하지 못했습니다{(' — ' + detail) if detail else ''}.")
    ans = input(f"           로봇이 실제로 '{label}' 상태입니까? "
                "(y=작업자 확인으로 진행 / 그 외=중단) > ").strip().lower()
    if ans == "y":
        print(f"           → 작업자 육안 확인으로 진행 (통신 확인 없음, 기록에 남김)")
        return True
    return False


def check_code(code, what):
    if code in (0, None):
        return
    if code in RPC_ERR:
        raise RealCommandError(f"{what} 실패 (code={code}) — {RPC_ERR[code]}",
                               timeout=(code == RPC_TIMEOUT))
    raise RealCommandError(
        f"{what} 거부 (code={code}) — 현재 FSM 에서 허용되지 않는 전이. 멘토 확인.")


# ── 실기체 링크 ───────────────────────────────────────────────────────
class G1Link:
    """LocoClient + G1ArmActionClient 를 반환코드 검사와 함께 묶은 래퍼."""

    def __init__(self, iface, domain=0, timeout=10.0, with_arm=True,
                 with_audio=False, volume=None, tts=False):
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
        self.tts_enabled = False   # 기본: 우리 TTS 를 쓰지 않는다
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
                self.tts_enabled = bool(tts)
            except Exception as e:
                print(f"  [오디오] 초기화 실패({e}) — 음성/LED 없이 계속 진행합니다.")
                self.audio = None

    # ── 음성·LED (실패해도 무시 — 제어를 막지 않는다) ────────────────
    def say(self, text, speaker_id=0):
        """TTS — 기본적으로 아무것도 하지 않는다.

        G1 의 TtsMaker 는 한국어를 지원하지 않고 영어 발음도 부정확해서,
        모드 전환 안내는 **로봇 자체의 내장 음성**에 맡긴다(레디/레귤러 등).
        우리 문구를 굳이 말하게 하려면 tts=True 로 생성한다.
        """
        if self.audio is None or not self.tts_enabled:
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
    def fsm(self, retries=2):
        """현재 FSM ID. 조회 실패 시 None (→ 육안 판정으로 대체).

        무선 링크에서는 GetFsmId(RPC 왕복)가 간헐적으로 실패한다. 한 번 실패했다고
        None 을 그대로 쓰면 '상태를 모른다'와 '통신이 튀었다'를 구분하지 못하므로
        몇 번 재시도한다.
        """
        for attempt in range(retries + 1):
            try:
                code, val = self.loco.GetFsmId()
                if code == 0:
                    return val
            except Exception:
                pass
            if attempt < retries:
                time.sleep(0.3)
        return None

    def fsm_mode(self):
        """GetFsmMode(7002) — GetFsmId 와 다른 값이다."""
        try:
            code, val = self.loco.GetFsmMode()
            return val if code == 0 else None
        except Exception:
            return None

    def balance_mode(self):
        """GetBalanceMode(7003)."""
        try:
            code, val = self.loco.GetBalanceMode()
            return val if code == 0 else None
        except Exception:
            return None

    def state_text(self):
        """조회 가능한 상태값을 한 줄로 — 대응표를 만들기 위한 관측용."""
        return (f"fsm_id={self.fsm()} / fsm_mode={self.fsm_mode()} "
                f"/ balance={self.balance_mode()}")

    def fsm_text(self):
        f = self.fsm()
        if f is None:
            return "조회 불가"
        return f"{f} ({FSM_NAME.get(f, '미상')})"

    # ── FSM 전이 (반환 코드 검사 O) ──────────────────────────────────
    def set_fsm(self, fsm_id, label=None, retries=2):
        """SetFsmId 를 직접 호출해 반환 코드를 검사한다.

        무선 링크에서는 RPC 응답이 늦어 3104(시간 초과)가 자주 난다.
        시간 초과는 '명령이 안 갔다'가 아니라 '답을 못 받았다'는 뜻이므로,
        FSM 을 다시 읽어 이미 목표 상태면 성공으로 처리하고 아니면 재시도한다.
        상태 거부(다른 코드)는 재시도해도 소용없으므로 즉시 예외를 던진다.
        """
        what = label or f"SetFsmId({fsm_id})"

        # 주의: '이미 그 상태면 생략' 같은 최적화를 넣지 말 것.
        # 실기체에서 GetFsmId 가 SetFsmId 로 보낸 번호와 다른 값을 돌려주는 것이
        # 관측됐다(4 로 전이한 뒤에도 200 으로 읽힘). 조회값을 근거로 전송을
        # 건너뛰면 실제로 필요한 전이를 빠뜨린다. 같은 번호를 다시 보내는 것은
        # 무해하므로 항상 보낸다.

        for attempt in range(1, retries + 2):
            code = self.loco.SetFsmId(fsm_id)
            if code in (0, None):
                return
            if code != RPC_TIMEOUT:
                check_code(code, what)
            print(f"      [통신] {what} 응답 시간 초과 "
                  f"(시도 {attempt}/{retries + 1}) — 상태 재확인 중")
            time.sleep(0.5)
            if self.fsm() == fsm_id:
                print(f"      명령은 반영됨 (FSM {fsm_id}) — 응답만 유실된 것으로 판단")
                return
        raise RealCommandError(
            f"{what} — 응답 시간 초과가 {retries + 1}회 반복. 통신 상태를 확인하세요 "
            f"(무선이면 유선 권장).", timeout=True)

    def damp(self):
        self.set_fsm(FSM.DAMP, "Damp")

    def wait_fsm(self, expect, settle=3.0, timeout=12.0, label=""):
        """기대 FSM 도달 대기. 도달하면 True, 시간초과면 False(육안 판정).

        ※ 실기체에서 GetFsmId 의 반환값이 SetFsmId 로 보낸 번호와 일치하지 않는
          것이 관측됐다. 따라서 이 함수의 결과는 '참고'이지 '판정'이 아니다.
          최종 판단은 항상 작업자의 육안 확인이다.
        """
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


def safe_exit(link, reason, damp=False):
    """빠져나올 때의 수렴점.

    damp=False (기본): 이동 정지 + 팔 반납만 하고 **현재 자세를 유지**한다.
      서 있는 로봇에 Damp 를 보내면 힘이 빠져 주저앉는다. 균형 제어/잠금 기립
      상태에서 그냥 멈추는 편이 대개 더 안전하고, 다음 시도도 바로 이어갈 수 있다.
    damp=True: 명시적으로 Damp 까지 보낸다. 행어가 하중을 받을 준비가 된
      경우에만 쓴다.
    """
    if damp:
        banner(f"[안전] {reason} → 정지 + Damp 수렴 (행어가 하중을 받는다)")
    else:
        banner(f"[안전] {reason} → 이동 정지 · 팔 반납 · 현재 자세 유지")
    try:
        link.stop_move()
    except Exception:
        pass
    try:
        link.release_arm()
    except Exception:
        pass
    if not damp:
        try:
            link.led("error")
        except Exception:
            pass
        # 통신이 끊긴 상태에서 여기서 또 RPC 를 걸면 같이 멈춘다 — 실패해도 넘어간다.
        try:
            print(f"      현재 FSM: {link.fsm_text()}")
        except Exception:
            print("      현재 FSM: 조회 불가(통신 문제)")
        print("      로봇은 여전히 자세를 유지 중이다 — 필요하면 리모컨으로 Damp.")
        return
    safe_damp(link, reason)


def safe_damp(link, reason):
    """명시적으로 Damp 까지 보내는 경로. 행어 하중 준비가 됐을 때만."""
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
