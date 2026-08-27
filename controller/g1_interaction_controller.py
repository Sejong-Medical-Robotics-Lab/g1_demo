#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_combined_action.py — 카메라 포즈 인식 + PC 마이크 음성 명령을 동시에
받아 G1 액션을 실행한다.

    [메인 스레드]   카메라 → MediaPipe Holistic → 포즈 판별 ──┐
    [백그라운드]     PC 마이크 → Google STT → 키워드 매칭  ────┤→ 공유 쿨다운 상태 → G1 팔 액션
                                                              ┘

g1_pose_action.py 와 g1_voice_action.py 를 합친 것이다. 로봇은 한
번에 하나의 팔 동작만 할 수 있으므로, 포즈 인식 스레드와 음성 인식
스레드가 **같은 쿨다운/타이머 상태(SharedActionState)를 락으로 공유**한다.
한쪽에서 액션을 쏘면 다른 쪽도 그 쿨다운이 끝날 때까지는 새 액션을
못 쏜다 — 안 그러면 포즈로 막 액션을 쏜 순간 음성 명령이 끼어들어
로봇이 동작 중간에 다른 동작으로 튀는 문제가 생긴다.

카메라 창(OpenCV)은 GUI 스레드 제약 때문에 메인 스레드에서 돌리고,
음성 인식(마이크 listen 이 블로킹)은 데몬 스레드에서 따로 돈다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
준비 (PC)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    pip install mediapipe opencv-python
    sudo apt install portaudio19-dev
    pip3 install SpeechRecognition pyaudio --user

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
실행
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
① 개발·연습 — 노트북 웹캠 + 마이크, 로봇 없이
     python3 g1_combined_action.py --source 0 --dry-run

② 실전 — 로봇을 FSM 501 로 올린 뒤
     g1
     python3 g1_stand_test.py --iface $G1_IFACE
     python3 g1_combined_action.py --iface $G1_IFACE
     python3 g1_combined_action.py --source 0 --dry-run          # 웹캠+마이크 둘 다 테스트
     python3 g1_combined_action.py --iface $G1_IFACE              # 실전, 포즈+음성 동시
     python3 g1_combined_action.py --iface $G1_IFACE --no-voice   # 포즈만
     
     
     python3 g1_combined_action.py --iface $G1_IFACE --no-pose --mic-index 8  # 음성만

  · 포즈나 음성 중 하나만 쓰고 싶으면 --no-voice 또는 --no-pose
  · q 또는 Esc(카메라 창) / Ctrl+C 로 종료
  · "그만"/"놓아"/"릴리즈" 라고 말하면 팔 제어권을 반납한다(release, 99)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Jetson 쪽 카메라 서버 — 반드시 g1_rgbd_server.py 를 띄울 것
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    (Jetson) python3 g1_rgbd_server.py

  · 거리 안전 게이트(사람이 --min-distance 보다 가까우면 액션 차단)가
    g1_person_distance.request_depth() 로 /depth?x=&y= 를 질의한다.
    이 엔드포인트는 g1_rgbd_server.py 에만 있다 — 예전 g1_cam_server.py
    (MJPEG만 서빙)로는 거리를 못 재서 항상 "NO DEPTH"로 막힌다.
  · /stream 경로는 두 서버가 동일하므로 --source 인자는 안 바꿔도 된다.
  · 주의: RealSense는 한 프로세스만 물 수 있다. g1_cam_server.py 나
    Unitree 기본 videohub_pc4 서비스가 먼저 카메라를 잡고 있으면
    g1_rgbd_server.py 가 pyrealsense2 초기화에서 실패한다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
안전
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
· 로봇은 제자리에 서 있고 팔만 움직인다. 보행 명령을 보내지 않는다.
· ALLOWED_ACTION_IDS 화이트리스트에 없는 ID는 절대 실행하지 않는다.
· 포즈/음성 두 입력이 같은 쿨다운을 공유해서 서로 씹거나 겹치지 않는다.
· 쿨다운(=화면 타이머)이 끝나는 순간 강제로 release 를 보내 로봇 상태와
  타이머를 맞춘다.
· 거리 안전 게이트: 사람이 --min-distance(기본 1.0m) 보다 가까우면
  포즈/음성 어느 쪽에서 트리거됐든 액션을 막는다(release 는 예외).
  깊이 정보가 아예 없으면("NO DEPTH") 안전 쪽으로 판단해 역시 막는다.
  --no-pose(음성 전용) 모드에서는 카메라 프레임이 없어 거리를 잴 수
  없으므로 게이트가 자동으로 꺼진다. --no-safety 로 수동으로도 끌 수 있다.
· 종료 시 팔 제어권을 반납한다(release arm, 액션 99).
"""
import argparse
import os
import sys
import threading
import time

import cv2
import speech_recognition as sr

from g1_speech import Speaker
from g1_person_distance import get_body_center, request_depth

# speech/ 폴더는 "실행한 위치(cwd)"가 아니라 이 스크립트 파일 위치 기준으로 찾는다.
# 다른 디렉토리에서 python3 g1_P_A_action.py 를 실행해도 wav 를 못 찾는 문제를 막기 위함.
SPEECH_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "speech")

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
ACTION_LEFT_HAND_UP = 23      # 왼손 전용 ID가 SDK에 없어서 오른손 ID로 대신 실행 (확정된 설계)
ACTION_XRAY = 24              # ultraman_ray
ACTION_FACE_WAVE = 25         # wave_under_head
ACTION_WAVE = 26              # wave_above_head
ACTION_SHAKE_HAND = 27        # shake_hand
ACTION_RELEASE = 99           # release_arm

# ── 액션 실행 시 같이 내보낼 음성 (speech/ 폴더의 16kHz mono wav) ──────
# 없는 액션은 그냥 무음으로 지나간다. 파일 추가만 하면 늘릴 수 있다.
SPEECH_MAP = {
    ACTION_WAVE:           "hello.wav",
    ACTION_BOTH_HANDS_UP:  "manse.wav",
    ACTION_TWO_HAND_KISS:  "kiss.wav",
    ACTION_LEFT_KISS:      "kiss.wav",
    ACTION_RIGHT_KISS:     "kiss.wav",
    ACTION_CLAP:           "clap.wav",
    ACTION_HIGH_FIVE:      "highfive.wav",
    ACTION_HUG:            "hug.wav",
    ACTION_TWO_HAND_HEART: "heart.wav",
    ACTION_RIGHT_HEART:    "heart.wav",
    ACTION_REJECT:         "refuse.wav",
    ACTION_XRAY:           "xray.wav",
    ACTION_SHAKE_HAND:     "shake.wav",
}

# 안전장치: 이 화이트리스트에 없는 ID는 절대 arm.ExecuteAction() 으로 보내지 않는다.
# 하체(보행 등) 관련 ID는 이 리스트에 절대 추가하지 않는다 — 그게 이 안전장치의 존재 이유.
ALLOWED_ACTION_IDS = {
    11, 12, 13, 15, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 99,
}

FSM_REGULAR = 501             # 팔 액션은 이 상태에서만 동작한다
ACTION_COOLDOWN = 8.0         # 동작 실행 후 기본으로 이만큼은 새 동작을 무시한다
# 액션 ID별 실제 소요시간(초). 실측하면서 채워나갈 것 — 없으면 기본값 사용.
ACTION_DURATION_S = {
    # 예시: ACTION_TWO_HAND_KISS: 4.0,
}

# ══════════════════════════════════════════════════════════════════════
# 포즈 인식 
# ══════════════════════════════════════════════════════════════════════

HOLD_FRAMES = 3          # 같은 자세가 이만큼 연속으로 잡혀야 인정
MIN_VIS = 0.6            # 관절 신뢰도 최소값

KISS_MAX_DIST = 0.12     # 정규화 좌표 기준, 손목-코 거리 이 이하면 "얼굴 근처"

WAVE_MIN_DELTA = 0.02    # 노이즈 무시할 최소 이동량
UP_HOLD_SECONDS = 0.8    # 이 시간 동안 방향전환 없으면 "든 상태(정지)"로 확정
MIN_UP_SAMPLES = 3       # 시간이 지나도 이만큼 프레임을 못 봤으면 still 확정을 미룬다

# MediaPipe Pose 랜드마크 번호
NOSE = 0
MOUTH_LEFT, MOUTH_RIGHT = 9, 10
L_SHOULDER, R_SHOULDER = 11, 12
L_ELBOW, R_ELBOW = 13, 14
L_WRIST, R_WRIST = 15, 16

# MediaPipe Hands 랜드마크 번호 (Holistic 의 left_hand_landmarks/right_hand_landmarks)
HAND_WRIST = 0
HAND_THUMB_TIP = 4
HAND_INDEX_TIP = 8
HAND_INDEX_MCP = 5
HAND_MIDDLE_TIP = 12
HAND_MIDDLE_MCP = 9
HAND_RING_TIP = 16
HAND_RING_MCP = 13
HAND_PINKY_TIP = 20
HAND_PINKY_MCP = 17

HEART_PINCH_RATIO = 0.35  # 엄지-검지 끝 거리 / 손 크기 — 이 이하면 "붙었다"
HEART_CURL_RATIO = 1.05   # 손가락끝-손목 거리 / 뿌리마디-손목 거리 — 이 이하면 "접혔다"
DEBUG_HEART = False        # 콘솔에 손하트 판별 값 실시간 출력

ELBOW_TOUCH_RATIO = 0.5   # 손목-반대쪽팔꿈치 거리 / 팔뚝 길이 — 이 이하면 "닿음"
DEBUG_XRAY = False         # 콘솔에 엑스레이 판별 값 실시간 출력


def new_wave_state():
    """손 하나(왼손 또는 오른손)의 흔들기 판별 상태를 담는 dict.

    phase: None(내려간 상태) / 'pending'(방금 올라가 판정 중) /
           'still'(든 상태로 확정) / 'wave'(흔든 것으로 확정, 락)
    """
    return {"phase": None, "since": None, "extreme": None, "dir": None, "count": 0}


def update_wave_state(now, is_up, wrist_x, state):
    """손 하나의 상태를 프레임마다 갱신하고 현재 phase 를 리턴한다."""
    if not is_up:
        state["phase"] = None
        state["since"] = None
        state["extreme"] = None
        state["dir"] = None
        state["count"] = 0
        return None

    if state["phase"] is None:
        state["phase"] = "pending"
        state["since"] = now
        state["extreme"] = wrist_x
        state["dir"] = None
        state["count"] = 1
        return "pending"

    if state["phase"] == "wave":
        return "wave"

    state["count"] += 1

    delta = wrist_x - state["extreme"]
    if abs(delta) >= WAVE_MIN_DELTA:
        new_dir = 1 if delta > 0 else -1
        if state["dir"] is not None and new_dir != state["dir"]:
            state["phase"] = "wave"
            return "wave"
        state["dir"] = new_dir
        state["extreme"] = wrist_x

    if (state["phase"] == "pending"
            and (now - state["since"]) >= UP_HOLD_SECONDS
            and state["count"] >= MIN_UP_SAMPLES):
        state["phase"] = "still"

    return state["phase"]


def dist(a, b):
    """두 랜드마크 사이 유클리드 거리 (정규화 좌표 기준)."""
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5


def is_finger_heart(hand_landmarks, tag=""):
    """엄지-검지를 붙이고 나머지 손가락을 접은 '손가락 하트' 모양인지 판정."""
    if hand_landmarks is None:
        if DEBUG_HEART and tag:
            print(f"    [DEBUG-HEART {tag}] 손 랜드마크 자체가 안 잡힘 (None)")
        return False
    lm = hand_landmarks.landmark

    hand_size = dist(lm[HAND_WRIST], lm[HAND_MIDDLE_MCP])
    if hand_size < 1e-6:
        return False

    pinch = dist(lm[HAND_THUMB_TIP], lm[HAND_INDEX_TIP])
    pinch_ratio = pinch / hand_size
    curls = []
    for tip, mcp in ((HAND_MIDDLE_TIP, HAND_MIDDLE_MCP),
                     (HAND_RING_TIP, HAND_RING_MCP),
                     (HAND_PINKY_TIP, HAND_PINKY_MCP)):
        mcp_to_wrist = dist(lm[mcp], lm[HAND_WRIST])
        curl_ratio = dist(lm[tip], lm[HAND_WRIST]) / mcp_to_wrist if mcp_to_wrist >= 1e-6 else 999
        curls.append(curl_ratio)

    if DEBUG_HEART and tag:
        print(f"    [DEBUG-HEART {tag}] pinch={pinch_ratio:.2f}(기준<{HEART_PINCH_RATIO}) "
              f"curl(중/약/새끼)={[f'{c:.2f}' for c in curls]}(기준<{HEART_CURL_RATIO})")

    if pinch_ratio > HEART_PINCH_RATIO:
        return False
    if any(c > HEART_CURL_RATIO for c in curls):
        return False

    return True


def is_elbow_cross_pose(lm):
    """한쪽 손목이 반대쪽 팔꿈치에 닿아있으면 엑스레이 자세로 인정.

    양쪽이 동시에 붙어있을 필요는 없다 — 한쪽만 닿아도 인정한다.
    """
    def ok(i):
        return lm[i].visibility >= MIN_VIS

    triggered = False

    if ok(L_WRIST) and ok(R_ELBOW) and ok(R_WRIST):
        r_forearm = dist(lm[R_ELBOW], lm[R_WRIST])
        if r_forearm >= 1e-6:
            l_ratio = dist(lm[L_WRIST], lm[R_ELBOW]) / r_forearm
            if DEBUG_XRAY:
                print(f"    [DEBUG-XRAY] 왼손목→오른팔꿈치 ratio={l_ratio:.2f} "
                      f"(기준 <= {ELBOW_TOUCH_RATIO})")
            if l_ratio <= ELBOW_TOUCH_RATIO:
                triggered = True

    if ok(R_WRIST) and ok(L_ELBOW) and ok(L_WRIST):
        l_forearm = dist(lm[L_ELBOW], lm[L_WRIST])
        if l_forearm >= 1e-6:
            r_ratio = dist(lm[R_WRIST], lm[L_ELBOW]) / l_forearm
            if DEBUG_XRAY:
                print(f"    [DEBUG-XRAY] 오른손목→왼팔꿈치 ratio={r_ratio:.2f} "
                      f"(기준 <= {ELBOW_TOUCH_RATIO})")
            if r_ratio <= ELBOW_TOUCH_RATIO:
                triggered = True

    return triggered


def kiss_signal(lm, wrist_idx, hand_landmarks):
    """이 손이 뽀뽀 동작 중인지 판정."""
    if lm[MOUTH_LEFT].visibility >= MIN_VIS and lm[MOUTH_RIGHT].visibility >= MIN_VIS:
        mouth_x = (lm[MOUTH_LEFT].x + lm[MOUTH_RIGHT].x) / 2
        mouth_y = (lm[MOUTH_LEFT].y + lm[MOUTH_RIGHT].y) / 2
    elif lm[NOSE].visibility >= MIN_VIS:
        mouth_x, mouth_y = lm[NOSE].x, lm[NOSE].y
    else:
        return False

    if hand_landmarks is not None:
        tip = hand_landmarks.landmark[HAND_MIDDLE_TIP]
        dx, dy = tip.x - mouth_x, tip.y - mouth_y
        return (dx * dx + dy * dy) ** 0.5 <= KISS_MAX_DIST

    if lm[wrist_idx].visibility < MIN_VIS or lm[NOSE].visibility < MIN_VIS:
        return False
    dx = lm[wrist_idx].x - lm[NOSE].x
    dy = lm[wrist_idx].y - lm[NOSE].y
    return (dx * dx + dy * dy) ** 0.5 <= KISS_MAX_DIST


def classify(lm, left_hand, right_hand, l_state, r_state, now):
    """관절 좌표에서 행동을 판별한다. (자세한 설명은 g1_pose_action.py 참고)

    판정 우선순위: 키스(입 근처) > 손하트(손 모양) > 엑스레이(팔뚝 교차) >
    흔들기/올림.
    """
    def ok(i):
        return lm[i].visibility >= MIN_VIS

    if not (ok(L_SHOULDER) and ok(R_SHOULDER)):
        update_wave_state(now, False, 0.0, l_state)
        update_wave_state(now, False, 0.0, r_state)
        return None, "어깨가 안 보임"

    l_kiss = kiss_signal(lm, L_WRIST, left_hand)
    r_kiss = kiss_signal(lm, R_WRIST, right_hand)

    if l_kiss or r_kiss:
        update_wave_state(now, False, 0.0, l_state)
        update_wave_state(now, False, 0.0, r_state)
        if l_kiss and r_kiss:
            return "two_hand_kiss", "양손 키스"
        if r_kiss:
            return "right_kiss", "오른손 키스"
        return "left_kiss", "왼손 키스"

    l_heart = is_finger_heart(left_hand, tag="L")
    r_heart = is_finger_heart(right_hand, tag="R")

    if l_heart or r_heart:
        update_wave_state(now, False, 0.0, l_state)
        update_wave_state(now, False, 0.0, r_state)
        return "two_hand_heart", "손하트"

    if is_elbow_cross_pose(lm):
        update_wave_state(now, False, 0.0, l_state)
        update_wave_state(now, False, 0.0, r_state)
        return "xray", "엑스레이(팔뚝 교차)"

    sh_y = (lm[L_SHOULDER].y + lm[R_SHOULDER].y) / 2

    l_up = ok(L_WRIST) and lm[L_WRIST].y < sh_y
    r_up = ok(R_WRIST) and lm[R_WRIST].y < sh_y

    l_phase = update_wave_state(now, l_up, lm[L_WRIST].x if l_up else 0.0, l_state)
    r_phase = update_wave_state(now, r_up, lm[R_WRIST].x if r_up else 0.0, r_state)

    if l_up and r_up:
        return "both_hands_up", "양손 올림"
    if r_phase == "wave":
        return "right_hand_wave", "오른손 흔듦"
    if l_phase == "wave":
        return "left_hand_wave", "왼손 흔듦"
    if r_phase == "still":
        return "right_hand_up", "오른손 올림 (정지)"
    if l_phase == "still":
        return "left_hand_up", "왼손 올림 (정지)"
    if r_phase == "pending":
        return None, "오른손 올림 (판정 중…)"
    if l_phase == "pending":
        return None, "왼손 올림 (판정 중…)"

    return None, "대기"


POSE_ACTION_MAP = {
    "right_hand_up":   (ACTION_RIGHT_HAND_UP, "G1 오른손 올리기"),
    "right_hand_wave": (ACTION_WAVE,          "G1 오른손 흔들기"),
    "left_hand_up":    (ACTION_LEFT_HAND_UP,  "G1 왼손 올리기 (오른손 액션으로 대신 실행)"),
    "left_hand_wave":  (ACTION_WAVE,          "G1 왼손 흔들기 (오른손 액션으로 대신 실행)"),
    "both_hands_up":   (ACTION_BOTH_HANDS_UP, "G1 양팔 올리기"),
    "two_hand_kiss":   (ACTION_TWO_HAND_KISS, "G1 양손 뽀뽀"),
    "left_kiss":       (ACTION_LEFT_KISS,     "G1 왼손 뽀뽀"),
    "right_kiss":      (ACTION_RIGHT_KISS,    "G1 오른손 뽀뽀"),
    "two_hand_heart":  (ACTION_TWO_HAND_HEART, "G1 양손 하트"),
    "xray":            (ACTION_XRAY,           "G1 엑스레이 (울트라맨 광선)"),
}

# ══════════════════════════════════════════════════════════════════════
# 음성 인식 
# ══════════════════════════════════════════════════════════════════════

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
    (["레이저", "울트라맨", "액션빔"],       ACTION_XRAY,           "엑스레이"),
    (["얼굴 흔들어"],                     ACTION_FACE_WAVE,      "얼굴 앞 흔들기"),
    (["흔들어", "안녕", "인사"],            ACTION_WAVE,           "손 흔들기"),
    (["악수"],                           ACTION_SHAKE_HAND,     "악수"),
    (["그만", "놓아", "릴리즈", "release"], ACTION_RELEASE,        "팔 제어권 반납"),
]


def match_command(text):
    """인식된 텍스트에서 명령을 찾는다. 못 찾으면 (None, None)."""
    text = text.replace(" ", "")
    for keywords, action_id, name in COMMAND_MAP:
        for kw in keywords:
            if kw.replace(" ", "") in text:
                return action_id, name
    return None, None


# ══════════════════════════════════════════════════════════════════════
# 공유 쿨다운 상태 — 포즈 스레드와 음성 스레드가 같이 씀
# ══════════════════════════════════════════════════════════════════════

def _execute_arm_action(arm, action_id):
    """arm.ExecuteAction() 을 실제로 부르는 부분. 항상 별도 스레드에서
    호출된다 — 호출한 쪽(카메라 메인 루프일 수도 있음)이 RPC 응답을
    기다리느라 멈추지 않게 하기 위함."""
    try:
        arm.ExecuteAction(action_id)
    except Exception as e:
        print(f"    액션 실패: {e}")


class SharedActionState:
    """포즈/음성 두 입력이 공유하는 쿨다운·타이머 상태. 락으로 보호한다.

    거리 안전 게이트도 여기서 같이 관리한다 — 포즈 스레드가 주기적으로
    측정한 최신 거리를 update_distance() 로 넣어두면, try_trigger() 가
    포즈든 음성이든 트리거 시점에 그 최신 거리로 안전 여부를 판단한다.
    한곳에만 게이트를 두는 이유: 소스별로 따로 체크하면 음성 명령이
    거리 체크를 빼먹는 구멍이 생기기 쉽다.
    """

    def __init__(self, speaker=None, min_distance=None):
        self.speaker = speaker
        self.lock = threading.Lock()
        self.last_action_at = 0.0
        self.current_cooldown = ACTION_COOLDOWN
        self.release_pending = False
        self.executing_name = ""
        # 거리 안전 게이트. min_distance 가 None 이면 게이트 자체를 안 쓴다
        # (예: --no-pose 모드처럼 거리를 측정할 방법이 없는 경우).
        self.min_distance = min_distance
        self.last_distance = None
        # 메인(카메라) 루프는 몸통 중심 픽셀만 여기 적어두고 끝낸다.
        # 실제 request_depth() 네트워크 호출은 별도 depth_loop 스레드가
        # 이 값을 읽어가서 한다 — 메인 루프를 블로킹하지 않기 위함
        # (예전에는 메인 루프 안에서 직접 request_depth 를 불러서,
        #  요청당 최대 0.3초씩 카메라/포즈 인식이 멈추는 지연의 원인이었다).
        self.last_center_px = None

    def update_distance(self, distance_m):
        with self.lock:
            self.last_distance = distance_m

    def update_center_px(self, center_px):
        with self.lock:
            self.last_center_px = center_px

    def get_center_px(self):
        with self.lock:
            return self.last_center_px

    def safety_status(self):
        """(allowed, reason) 리턴. min_distance 가 설정 안 돼 있으면 항상 통과."""
        with self.lock:
            min_distance = self.min_distance
            distance_m = self.last_distance
        if min_distance is None:
            return True, "GATE OFF"
        if distance_m is None:
            return False, "NO DEPTH"
        if distance_m < min_distance:
            return False, "TOO CLOSE"
        return True, "SAFE"

    def is_cooling(self, now):
        with self.lock:
            return (now - self.last_action_at) < self.current_cooldown

    def remaining(self, now):
        with self.lock:
            return self.current_cooldown - (now - self.last_action_at)

    def try_trigger(self, arm, action_id, action_name, source_tag, now):
        """쿨다운 중이 아니고 거리가 안전하면 액션을 실행한다. 실행했으면 True."""
        # release(팔 풀기)는 "멈춰" 명령이라 거리와 무관하게 항상 통과시킨다.
        if action_id != ACTION_RELEASE:
            allowed, reason = self.safety_status()
            if not allowed:
                print(f"    [안전거리] {action_name} 차단됨 ({reason}) — 출처: {source_tag}")
                return False

        with self.lock:
            if (now - self.last_action_at) < self.current_cooldown:
                return False
            self.last_action_at = now
            self.current_cooldown = ACTION_DURATION_S.get(action_id, ACTION_COOLDOWN)
            self.release_pending = (action_id != ACTION_RELEASE)
            self.executing_name = action_name

        print(f"  [{time.strftime('%H:%M:%S')}] ({source_tag}) → {action_name} (ID {action_id})")
        if self.speaker is not None and action_id in ALLOWED_ACTION_IDS:
            self.speaker.say(action_id)

        if arm is not None:
            if action_id not in ALLOWED_ACTION_IDS:
                # 화이트리스트에 없는 ID — 절대 실행하지 않는다.
                print(f"    [안전] 액션 ID {action_id} 는 화이트리스트에 없어 실행하지 않음")
            else:
                # arm.ExecuteAction() 은 RPC 호출이라 응답이 늦어지면(네트워크
                # 지연 등) 그만큼 호출한 스레드가 멈춘다. 포즈 트리거는 이 함수를
                # 메인(카메라) 스레드에서 직접 부르기 때문에, 여기서 동기 호출하면
                # 응답 오는 동안 화면이 그대로 얼어붙는다. 그래서 speaker.say()와
                # 같은 방식으로 스레드에 던지고 바로 리턴한다.
                threading.Thread(
                    target=_execute_arm_action, args=(arm, action_id), daemon=True
                ).start()
        return True

    def check_release(self, arm, now):
        """쿨다운(=화면 타이머)이 끝나는 순간 강제로 release 를 보낸다."""
        with self.lock:
            if not self.release_pending:
                return
            if (now - self.last_action_at) < self.current_cooldown:
                return
            self.release_pending = False

        if arm is not None:
            print(f"  [{time.strftime('%H:%M:%S')}] 쿨다운 종료 → 강제 정지(release)")
            threading.Thread(
                target=_execute_arm_action, args=(arm, ACTION_RELEASE), daemon=True
            ).start()


# ══════════════════════════════════════════════════════════════════════
# 거리(depth) 질의 스레드 — 메인 카메라 루프를 블로킹하지 않기 위해 분리
# ══════════════════════════════════════════════════════════════════════

def depth_loop(args, state, stop_event):
    """request_depth() 는 HTTP 요청(최대 0.3초 블로킹)이라 메인 카메라
    루프 안에서 직접 부르면 그 시간만큼 포즈 인식·액션 트리거가 같이
    멎는다. 그래서 별도 스레드에서 최신 center_px 를 읽어다 자체
    주기로 질의하고, 결과만 state 에 적어둔다."""
    query_period = 1.0 / max(args.query_hz, 0.1)
    while not stop_event.is_set():
        t0 = time.monotonic()
        center_px = state.get_center_px()
        if center_px is not None:
            px, py = center_px
            distance_m = request_depth(args.depth_base, px, py, radius=args.radius)
            state.update_distance(distance_m)
        else:
            state.update_distance(None)
        elapsed = time.monotonic() - t0
        time.sleep(max(0.0, query_period - elapsed))


# ══════════════════════════════════════════════════════════════════════
# 음성 인식 스레드
# ══════════════════════════════════════════════════════════════════════

def voice_loop(args, arm, state, stop_event):
    recognizer = sr.Recognizer()
    mic = sr.Microphone(device_index=args.mic_index)

    print("  [음성] 마이크 주변 소음 보정 중…")
    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=1.0)
    print("  [음성] 준비 완료. 말씀하세요.\n")

    while not stop_event.is_set():
        now = time.monotonic()
        state.check_release(arm, now)  # 루프가 돌 때마다(최대 마이크 timeout 주기) 체크

        if state.speaker is not None and state.speaker.is_speaking():
            time.sleep(0.2)
            continue

        with mic as source:
            try:
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=4)
            except sr.WaitTimeoutError:
                continue

        if stop_event.is_set():
            break

        try:
            text = recognizer.recognize_google(audio, language="ko-KR")
        except sr.UnknownValueError:
            continue
        except sr.RequestError as e:
            print(f"  [음성][오류] STT 요청 실패(인터넷 확인): {e}")
            time.sleep(1.0)
            continue

        print(f"  [음성] 들림: \"{text}\"")
        action_id, action_name = match_command(text)
        if action_id is None:
            print("    → 매칭되는 명령 없음")
            continue

        now = time.monotonic()
        if not state.try_trigger(arm, action_id, action_name, "음성", now):
            left = state.remaining(now)
            print(f"    → 쿨다운 중 ({left:.1f}초 남음), 무시")


# ══════════════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(
        description="카메라 포즈 인식 + PC 마이크 음성 명령 → G1 대응 동작")
    ap.add_argument("--source", default="http://192.168.123.164:8080/stream",
                    help="영상 입력. 웹캠은 0, 로봇은 MJPEG URL (기본)")
    ap.add_argument("--iface", help="예: enx... (CYCLONEDDS_URI 설정 시 생략 가능)")
    ap.add_argument("--domain", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true",
                    help="로봇에 명령을 보내지 않고 인식만 확인")
    ap.add_argument("--no-window", action="store_true",
                    help="화면 표시 없이 콘솔로만")
    ap.add_argument("--no-voice", action="store_true", help="음성 인식 끄기 (포즈만)")
    ap.add_argument("--no-pose", action="store_true", help="포즈 인식 끄기 (음성만)")
    ap.add_argument("--mic-index", type=int, default=None,
                    help="마이크 장치 번호 (여러 개면 --list-mics 로 확인)")
    ap.add_argument("--list-mics", action="store_true",
                    help="사용 가능한 마이크 목록만 출력하고 종료")
    ap.add_argument("--depth-base", default="http://192.168.123.164:8080",
                    help="g1_rgbd_server.py 의 base URL (/depth 질의용)")
    ap.add_argument("--min-distance", type=float, default=1.0,
                    help="이보다 사람이 가까우면 액션을 막는다 (m)")
    ap.add_argument("--query-hz", type=float, default=5.0,
                    help="거리 질의 주기 (초당 횟수)")
    ap.add_argument("--radius", type=int, default=3,
                    help="/depth 질의 시 median 낼 픽셀 반경")
    ap.add_argument("--no-safety", action="store_true",
                    help="거리 안전 게이트를 끈다 (테스트용, 주의해서 사용)")
    args = ap.parse_args()

    if args.list_mics:
        for i, name in enumerate(sr.Microphone.list_microphone_names()):
            print(f"  [{i}] {name}")
        return

    if args.no_pose and args.no_voice:
        sys.exit("--no-pose 와 --no-voice 를 동시에 켜면 아무 입력도 없습니다.")

    mp = None
    if not args.no_pose:
        try:
            import mediapipe as mp
        except ImportError:
            sys.exit("\n  mediapipe 가 없습니다:  pip install mediapipe opencv-python\n"
                      "  (포즈 인식 없이 음성만 쓰려면 --no-pose 를 추가하세요)\n")

    # ── 로봇 연결 (포즈/음성 공용) ─────────────────────────────────────
    arm = None
    audio_client = None
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

        from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient
        audio_client = AudioClient()
        audio_client.SetTimeout(10.0)
        audio_client.Init()

    speaker = Speaker(audio_client, SPEECH_MAP, wav_dir=SPEECH_DIR)
    print(f"  [음성출력] wav 폴더: {SPEECH_DIR}")

    # 거리 안전 게이트: --no-pose(음성 전용)면 거리를 잴 카메라 프레임이
    # 없으므로 자동으로 끈다. --no-safety 는 수동 off.
    safety_active = not args.no_safety and not args.no_pose
    if args.no_pose and not args.no_safety:
        print("  [경고] --no-pose 모드라 거리를 측정할 수 없습니다 — "
              "거리 안전 게이트를 자동으로 끕니다. (--no-safety 와 동일 효과)")
    min_distance = args.min_distance if safety_active else None
    state = SharedActionState(speaker, min_distance=min_distance)
    if safety_active:
        print(f"  안전거리: {args.min_distance:.2f}m 미만이면 액션 차단 "
              f"(depth-base={args.depth_base})")
    stop_event = threading.Event()

    print(f"\n  모드: {'인식만 (로봇에 명령 안 보냄)' if args.dry_run else '실전'}")
    print(f"  포즈: {'끔' if args.no_pose else '켬'}   음성: {'끔' if args.no_voice else '켬'}")
    print(f"  판정: 같은 자세 {HOLD_FRAMES}프레임 연속 → 동작 실행")
    print(f"        실행 후 기본 {ACTION_COOLDOWN}초(액션별 실측값 있으면 그걸로) 동안 새 동작 무시\n")

    # ── 음성 스레드 시작 ────────────────────────────────────────────────
    voice_thread = None
    if not args.no_voice:
        voice_thread = threading.Thread(
            target=voice_loop, args=(args, arm, state, stop_event), daemon=True)
        voice_thread.start()

    # ── 거리 질의 스레드 시작 (메인 루프 블로킹 방지) ───────────────────
    depth_thread = None
    if safety_active:
        depth_thread = threading.Thread(
            target=depth_loop, args=(args, state, stop_event), daemon=True)
        depth_thread.start()

    # ── 포즈 인식 (메인 스레드) ─────────────────────────────────────────
    if not args.no_pose:
        cap = None
        holistic = None
        try:
            src = int(args.source) if str(args.source).isdigit() else args.source
            cap = cv2.VideoCapture(src)
            if not cap.isOpened():
                sys.exit(f"\n  영상을 열 수 없습니다: {args.source}\n"
                         "  · 로봇 카메라라면 Jetson 에서 g1_rgbd_server.py 가 떠 있는지\n"
                         "  · 웹캠이라면 --source 0\n")
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            holistic = mp.solutions.holistic.Holistic(
                model_complexity=1,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
                refine_face_landmarks=False)
            drawer = mp.solutions.drawing_utils
            style = mp.solutions.drawing_styles
            mp_holistic = mp.solutions.holistic

            print(f"  입력: {args.source}")
            print("  q 또는 Esc 로 종료\n")

            held, held_n = None, 0
            l_wave_state = new_wave_state()
            r_wave_state = new_wave_state()

            while True:
                ok, frame = cap.read()
                if not ok:
                    print("  프레임 수신 실패 — 재시도")
                    time.sleep(0.2)
                    continue

                now = time.monotonic()
                state.check_release(arm, now)

                h, w = frame.shape[:2]
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False
                res = holistic.process(rgb)

                label, desc = (None, "사람 없음")
                center_px = None
                if res.pose_landmarks:
                    lm = res.pose_landmarks.landmark
                    label, desc = classify(lm,
                                            res.left_hand_landmarks, res.right_hand_landmarks,
                                            l_wave_state, r_wave_state, now)
                    if safety_active:
                        center = get_body_center(lm)
                        if center is not None:
                            cx, cy = center
                            center_px = (int(cx * (w - 1)), int(cy * (h - 1)))
                else:
                    update_wave_state(now, False, 0.0, l_wave_state)
                    update_wave_state(now, False, 0.0, r_wave_state)

                if safety_active:
                    state.update_center_px(center_px)

                if label is not None and label == held:
                    held_n += 1
                else:
                    held, held_n = label, 1 if label else 0

                if label and held_n == HOLD_FRAMES:
                    action_id, action_name = POSE_ACTION_MAP[label]
                    state.try_trigger(arm, action_id, action_name, "포즈", now)

                if not args.no_window:
                    if res.pose_landmarks:
                        drawer.draw_landmarks(
                            frame, res.pose_landmarks,
                            mp_holistic.POSE_CONNECTIONS,
                            landmark_drawing_spec=style.get_default_pose_landmarks_style())
                    if res.left_hand_landmarks:
                        drawer.draw_landmarks(
                            frame, res.left_hand_landmarks, mp_holistic.HAND_CONNECTIONS)
                    if res.right_hand_landmarks:
                        drawer.draw_landmarks(
                            frame, res.right_hand_landmarks, mp_holistic.HAND_CONNECTIONS)

                    if center_px is not None:
                        cv2.circle(frame, center_px, 8, (255, 0, 255), -1)
                        cv2.circle(frame, center_px, 14, (255, 255, 255), 2)

                    bar = 40
                    cv2.rectangle(frame, (0, 0), (frame.shape[1], bar), (0, 0, 0), -1)
                    cv2.putText(frame, desc, (10, 27),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

                    if label:
                        w2 = int(frame.shape[1] * min(held_n / HOLD_FRAMES, 1.0))
                        cv2.rectangle(frame, (0, bar), (w2, bar + 5), (0, 200, 0), -1)

                    if safety_active:
                        allowed, reason = state.safety_status()
                        with state.lock:
                            dist_val = state.last_distance
                        dtext = "DISTANCE: --" if dist_val is None else f"DISTANCE: {dist_val:.2f} m"
                        scolor = (0, 255, 0) if allowed else (0, 0, 255)
                        cv2.putText(frame, dtext, (10, bar + 30),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                        cv2.putText(frame, f"SAFETY: {reason}", (10, bar + 58),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, scolor, 2)

                    if state.is_cooling(now):
                        left = state.remaining(now)
                        with state.lock:
                            exec_name = state.executing_name
                        cv2.putText(frame, f"{exec_name}  ({left:.1f}s)",
                                    (10, frame.shape[0] - 15),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2)

                    cv2.imshow("G1 Combined Action", frame)
                    if cv2.waitKey(1) & 0xFF in (ord('q'), 27):
                        break

        except KeyboardInterrupt:
            print("\n  중단")
        finally:
            if cap is not None:
                cap.release()
            cv2.destroyAllWindows()
            if holistic is not None:
                holistic.close()
    else:
        # 포즈 없이 음성만 — 메인 스레드는 그냥 voice_thread 가 끝날 때까지 대기
        try:
            while voice_thread is not None and voice_thread.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\n  중단")

    # ── 종료 정리 ───────────────────────────────────────────────────────
    stop_event.set()
    if voice_thread is not None:
        voice_thread.join(timeout=6.0)
    if depth_thread is not None:
        depth_thread.join(timeout=2.0)

    speaker.close()

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
