#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_voice_action.py — PC 마이크로 음성 명령을 받아 G1 액션을 실행한다.

    PC 마이크 → SpeechRecognition(Google Web STT, ko-KR) → 텍스트
              → 키워드 매칭 → G1 팔 액션

G1 자체 마이크는 안 쓴다 — Python SDK(unitree_sdk2py)의 AudioClient는
아직 ASR(음성인식)을 지원하지 않는다(TTS/LED만 가능, 2026-08 기준
GitHub 이슈로 확인됨). 그래서 PC 마이크로 대체한다.

음성 명령은 카메라 포즈 인식과 달리 상대방이 없어도 되므로, 원래
혼자서는 판별 불가능했던 clap/high_five/hug/shake_hand 같은 동작도
쓸 수 있다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
준비 (PC)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    sudo apt install portaudio19-dev   # pyaudio 빌드용 (리눅스)
    pip3 install SpeechRecognition pyaudio --break-system-packages

    구글 웹 STT를 쓰므로 PC가 인터넷에 연결돼 있어야 한다(로봇용
    이더넷 말고, 학교 WiFi 등 별도 인터넷 — 팀 문서에 나온 것과 동일한
    "eth0은 로봇용, wlan0은 인터넷용" 구조 그대로 쓰면 됨).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
실행
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
① 인식만 테스트 (로봇 없이)
     python3 g1_voice_action.py --dry-run

② 실전 — 로봇을 FSM 501 로 올린 뒤
     g1
     python3 g1_stand_test.py --iface $G1_IFACE
     python3 g1_voice_action.py --iface $G1_IFACE

  · Ctrl+C 로 종료
  · "그만"/"놓아"/"릴리즈" 라고 말하면 팔 제어권을 반납한다(release, 99)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
안전
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
· 로봇은 제자리에 서 있고 팔만 움직인다. 보행 명령을 보내지 않는다.
· ALLOWED_ACTION_IDS 화이트리스트에 없는 ID는 절대 실행하지 않는다
  (g1_pose_action.py 와 동일한 이중 안전장치).
· 동작을 보낸 뒤 ACTION_COOLDOWN 동안은 새 명령을 무시한다.
· 종료 시 팔 제어권을 반납한다(release arm, 액션 99).
"""
import argparse
import sys
import time

import speech_recognition as sr

# ── G1 팔 액션 ID (실기체 SDK 액션 리스트 확인값) ─────────────────────
ACTION_TWO_HAND_KISS = 11     # blow_kiss_with_both_hands
ACTION_LEFT_KISS = 12         # blow_kiss_with_left_hand
ACTION_RIGHT_KISS = 13        # blow_kiss_with_right_hand
ACTION_BOTH_HANDS_UP = 15     # both_hands_up
ACTION_CLAP = 17              # clamp (원문 표기 그대로)
ACTION_HIGH_FIVE = 18         # high_five
ACTION_HUG = 19               # hug
ACTION_TWO_HAND_HEART = 20    # make_heart_with_both_hands
ACTION_RIGHT_HEART = 21       # make_heart_with_right_hand
ACTION_REJECT = 22            # refuse
ACTION_RIGHT_HAND_UP = 23     # right_hand_up
ACTION_XRAY = 24              # ultraman_ray
ACTION_FACE_WAVE = 25         # wave_under_head
ACTION_HIGH_WAVE = 26         # wave_above_head
ACTION_SHAKE_HAND = 27        # shake_hand
ACTION_RELEASE = 99           # release_arm

# 안전장치: 이 화이트리스트에 없는 ID는 절대 arm.ExecuteAction() 으로 보내지 않는다.
# g1_pose_action.py 와 동일한 안전장치 — 하체 관련 ID는 절대 추가하지 않는다.
ALLOWED_ACTION_IDS = {
    11, 12, 13, 15, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 99,
}

FSM_REGULAR = 501             # 팔 액션은 이 상태에서만 동작한다
ACTION_COOLDOWN = 8.0         # 동작 실행 후 기본으로 이만큼은 새 명령을 무시한다
# 액션 ID별 실제 소요시간(초). 실측하면서 채워나갈 것 — 없으면 기본값(ACTION_COOLDOWN)
# 사용. g1_pose_action.py 와 동일한 방식.
ACTION_DURATION_S = {
    # 예시: ACTION_TWO_HAND_KISS: 4.0,
}

# ── 키워드 → 액션 매핑 ────────────────────────────────────────────────
# 구글 STT 인식 결과가 조금씩 달라질 수 있어서, 키워드 하나가 아니라
# 여러 표현을 리스트로 등록해서 부분 일치(in)로 매칭한다.
COMMAND_MAP = [
    (["뽀뽀", "키스"],                    ACTION_TWO_HAND_KISS,  "양손 뽀뽀"),
    (["왼손 뽀뽀"],                       ACTION_LEFT_KISS,      "왼손 뽀뽀"),
    (["오른손 뽀뽀"],                     ACTION_RIGHT_KISS,     "오른손 뽀뽀"),
    (["만세", "양손 들어", "손 들어"],      ACTION_BOTH_HANDS_UP,  "양손 올리기"),
    (["박수", "짝짝"],                    ACTION_CLAP,           "박수"),
    (["하이파이브", "하이 파이브"],         ACTION_HIGH_FIVE,      "하이파이브"),
    (["안아줘", "허그", "포옹"],            ACTION_HUG,            "허그"),
    (["하트", "사랑해"],                   ACTION_TWO_HAND_HEART, "양손 하트"),
    (["오른손 하트"],                     ACTION_RIGHT_HEART,    "오른손 하트"),
    (["싫어", "거절", "안돼"],              ACTION_REJECT,         "거절"),
    (["오른손 들어"],                     ACTION_RIGHT_HAND_UP,  "오른손 올리기"),
    (["레이저", "울트라맨","액션빔"],               ACTION_XRAY,           "엑스레이"),
    (["얼굴 흔들어"],                     ACTION_FACE_WAVE,      "얼굴 앞 흔들기"),
    (["흔들어", "안녕", "인사"],            ACTION_HIGH_WAVE,      "손 흔들기"),
    (["악수"],                           ACTION_SHAKE_HAND,     "악수"),
    (["그만", "놓아", "릴리즈", "release"], ACTION_RELEASE,        "팔 제어권 반납"),
]


def match_command(text):
    """인식된 텍스트에서 명령을 찾는다. 못 찾으면 None."""
    text = text.replace(" ", "")  # 띄어쓰기 차이로 놓치지 않게 정규화
    for keywords, action_id, name in COMMAND_MAP:
        for kw in keywords:
            if kw.replace(" ", "") in text:
                return action_id, name
    return None, None


def main():
    ap = argparse.ArgumentParser(description="PC 마이크 음성 명령 → G1 액션")
    ap.add_argument("--iface", help="예: enx... (CYCLONEDDS_URI 설정 시 생략 가능)")
    ap.add_argument("--domain", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true",
                    help="로봇에 명령을 보내지 않고 인식만 확인")
    ap.add_argument("--mic-index", type=int, default=None,
                    help="마이크 장치 번호 (여러 개면 --list-mics 로 확인)")
    ap.add_argument("--list-mics", action="store_true",
                    help="사용 가능한 마이크 목록만 출력하고 종료")
    args = ap.parse_args()

    if args.list_mics:
        for i, name in enumerate(sr.Microphone.list_microphone_names()):
            print(f"  [{i}] {name}")
        return

    # ── 로봇 연결 ────────────────────────────────────────────────────
    arm = None
    if not args.dry_run:
        import os
        from unitree_sdk2py.core.channel import ChannelFactoryInitialize
        from unitree_sdk2py.g1.arm.g1_arm_action_client import G1ArmActionClient
        from unitree_sdk2py.g1.loco.g1_loco_client import LocoClient

        if os.environ.get("CYCLONEDDS_URI"):
            ChannelFactoryInitialize(args.domain)
        else:
            if not args.iface:
                sys.exit("--iface 가 필요합니다 (또는 g1 으로 CYCLONEDDS_URI 설정).")
            ChannelFactoryInitialize(args.domain, args.iface)

        loco = LocoClient()
        loco.SetTimeout(5.0)
        loco.Init()
        code, fsm = loco.GetFsmId()
        print(f"  현재 FSM: {fsm if code == 0 else '조회 실패'}")
        if code == 0 and fsm != FSM_REGULAR:
            print(f"  [경고] 레귤러 모드(FSM {FSM_REGULAR})가 아닙니다 — "
                  "팔 액션이 code=7404 로 거부됩니다.")
            print("         먼저 g1_stand_test.py 로 501 까지 올리세요.")

        arm = G1ArmActionClient()
        arm.SetTimeout(10.0)
        arm.Init()

    # ── 마이크 ───────────────────────────────────────────────────────
    recognizer = sr.Recognizer()
    mic = sr.Microphone(device_index=args.mic_index)

    print(f"\n  모드: {'인식만 (로봇에 명령 안 보냄)' if args.dry_run else '실전'}")
    print("  마이크 주변 소음 보정 중…")
    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=1.0)
    print("  준비 완료. 말씀하세요. (Ctrl+C 로 종료)\n")

    last_action_at = 0.0
    release_pending = False       # 쿨다운이 끝나는 순간 강제 정지(release)할지
    current_cooldown = ACTION_COOLDOWN  # 방금 쏜 액션의 실제 소요시간(ACTION_DURATION_S 우선)

    try:
        while True:
            # 루프가 돌아올 때마다(최소 마이크 timeout 주기로) 쿨다운 종료 여부를 체크한다.
            # pose_action.py처럼 매 프레임 체크는 못 하지만(마이크 listen()이 블로킹이라),
            # 이 루프가 도는 시점마다 확인하면 최대 수 초 오차 내로 강제 정지된다.
            now = time.monotonic()
            if release_pending and (now - last_action_at) >= current_cooldown:
                release_pending = False
                if arm is not None:
                    try:
                        arm.ExecuteAction(ACTION_RELEASE)
                        print(f"  [{time.strftime('%H:%M:%S')}] 쿨다운 종료 → 강제 정지(release)")
                    except Exception as e:
                        print(f"    정지 실패: {e}")

            with mic as source:
                try:
                    audio = recognizer.listen(source, timeout=5, phrase_time_limit=4)
                except sr.WaitTimeoutError:
                    continue

            try:
                text = recognizer.recognize_google(audio, language="ko-KR")
            except sr.UnknownValueError:
                continue  # 알아듣지 못함 — 조용히 다시 듣기
            except sr.RequestError as e:
                print(f"  [오류] STT 요청 실패(인터넷 확인): {e}")
                time.sleep(1.0)
                continue

            print(f"  들림: \"{text}\"")
            action_id, action_name = match_command(text)

            if action_id is None:
                print("    → 매칭되는 명령 없음")
                continue

            now = time.monotonic()
            if (now - last_action_at) < current_cooldown:
                left = current_cooldown - (now - last_action_at)
                print(f"    → 쿨다운 중 ({left:.1f}초 남음), 무시")
                continue

            print(f"    → {action_name} (ID {action_id})")
            last_action_at = now
            current_cooldown = ACTION_DURATION_S.get(action_id, ACTION_COOLDOWN)

            if arm is not None:
                if action_id not in ALLOWED_ACTION_IDS:
                    print(f"    [안전] 액션 ID {action_id} 는 화이트리스트에 없어 실행하지 않음")
                else:
                    try:
                        arm.ExecuteAction(action_id)
                        # release 자체를 실행한 경우엔 다시 release를 걸 필요 없음
                        release_pending = (action_id != ACTION_RELEASE)
                    except Exception as e:
                        print(f"    액션 실패: {e}")

    except KeyboardInterrupt:
        print("\n  중단")
    finally:
        if arm is not None:
            try:
                print("  팔 제어권 반납")
                arm.ExecuteAction(ACTION_RELEASE)
                time.sleep(1.0)
            except Exception:
                pass
        print("  종료\n")


if __name__ == "__main__":
    main()
