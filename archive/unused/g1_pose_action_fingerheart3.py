#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_pose_action.py — 사람 자세를 인식해 G1 의 대응 동작을 실행한다.

시나리오 4단계. **모방이 아니라 대응**이다 — 사람의 관절 각도를 실시간으로
로봇 관절에 복사하는 것이 아니라, 미리 정한 몇 가지 행동을 판별해서
그에 맞는 G1 의 사전 정의 동작을 실행한다.

    카메라 → MediaPipe Pose → 관절 좌표 → 행동 판별 → G1 팔 액션

    사람이 오른손을 들고 가만히 있음, 사람이 왼손을 들고 가만히 있음  →  right_hand_up
    사람이 오른손을 흔듦, 사람이 왼손을 흔듦            →  high_wave
    사람이 양손을 올림               →  both_hands_up
    사람이 오른손을 얼굴 근처로      →  right_kiss
    사람이 왼손을 얼굴 근처로        →  left_kiss
    사람이 양손을 얼굴 근처로        →  two_hand_kiss
    사람이 손가락 하트(어느 손이든)  →  two_hand_heart

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
구조 — 왜 PC 에서 인식하나
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    [Jetson]  카메라 → MJPEG (g1_cam_server.py)
                  ↓ HTTP
    [PC]      영상 → MediaPipe → 판별 → SDK → G1

  · **MediaPipe 는 Jetson(aarch64)에 설치하기 어렵다.** 공식 wheel 이
    x86_64 와 라즈베리파이용뿐이라, Jetson 은 커뮤니티 빌드를 쓰거나
    Bazel 로 직접 빌드해야 한다. PC 에서는 `pip install mediapipe` 로 끝난다.
  · ROS 를 아예 쓰지 않는다. Jetson(Foxy) 과 PC(Jazzy) 의 DDS 규약이 달라
    같은 도메인에 두면 노드가 죽는 문제를 통째로 피한다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
흔들기 판별 — 왜 이렇게 하나
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"손을 들었다"만으로는 흔드는지 가만히 있는지 구분이 안 된다. 손이
올라간 "순간"부터 작은 상태 기계(update_wave_state)로 판정한다:

  · 그 순간부터 UP_HOLD_SECONDS 안에 좌우로 WAVE_MIN_DELTA 이상
    방향전환이 감지되면 → 즉시 "wave"로 확정, 손 내릴 때까지 유지
  · UP_HOLD_SECONDS 가 지나도록 방향전환이 없으면 → "still"(그냥
    든 상태)로 확정

판정이 still/wave 로 "확정"되기 전(pending)에는 classify() 가 라벨을
None 으로 리턴한다 — 그래야 main() 의 액션 발동 카운터(HOLD_FRAMES)가
판정 중에 미리 쌓이지 않고, 확정된 뒤부터 정확히 시작된다. 이게 없으면
UP_HOLD_SECONDS 를 아무리 늘려도 "든 순간 곧바로 6프레임" 만에 액션이
나가버려 판정 시간이 사실상 무시된다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
준비 (PC)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    g1                                  # venv (SDK)
    pip install mediapipe opencv-python

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
실행
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
① 개발·연습 — 노트북 웹캠, 로봇 없이
     python3 g1_pose_action.py --source 0 --dry-run

② 로봇 카메라로 인식만 (로봇 팔은 안 움직임)
     python3 g1_pose_action.py --dry-run

③ 실전 — 로봇을 FSM 501 로 올린 뒤
     g1
     python3 g1_stand_test.py --iface $G1_IFACE
     python3 g1_pose_action.py --iface $G1_IFACE

  · `q` 또는 `Esc` 로 종료
  · 화면에 뼈대와 판별 결과가 표시된다. 발표 때 이 창을 띄워두면 좋다

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
안전
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
· 로봇은 제자리에 서 있고 팔만 움직인다. 보행 명령을 보내지 않는다.
· 팔이 크게 움직이므로 **주변에 사람이 없어야 한다.**
· 한 동작이 끝날 때까지 다음 동작을 받지 않는다(ACTION_COOLDOWN).
· 종료 시 팔 제어권을 반납한다(release arm, 액션 99).
"""
import argparse
import sys
import time

import cv2

# ── G1 팔 액션 ID (실기체 SDK 액션 리스트 확인값) ─────────────────────
ACTION_TWO_HAND_KISS = 11     # blow_kiss_with_both_hands
ACTION_LEFT_KISS = 12         # blow_kiss_with_left_hand
ACTION_RIGHT_KISS = 13        # blow_kiss_with_right_hand
ACTION_BOTH_HANDS_UP = 15     # both_hands_up
ACTION_TWO_HAND_HEART = 20    # make_heart_with_both_hands
ACTION_LEFT_HAND_UP = 23      # right_hand_up 을 임시 재사용 중 — 전용 ID 없음, 아래 TODO 참고
ACTION_RIGHT_HAND_UP = 23     # right_hand_up
ACTION_WAVE = 26              # wave_above_head
ACTION_RELEASE = 99           # release_arm
# TODO: left_hand_up / left_hand_wave 전용 ID가 실기체 리스트에 없어서
#       지금은 오른손 ID(23/26)를 임시로 재사용 중.

# 안전장치: 이 화이트리스트에 없는 ID는 절대 arm.ExecuteAction() 으로 보내지 않는다.
# 실기체 SDK 액션 리스트(상체/팔 제스처)에 있는 ID만 명시적으로 등록.
# 하체(보행 등) 관련 ID는 이 리스트에 절대 추가하지 않는다 — 그게 이 안전장치의 존재 이유.
ALLOWED_ACTION_IDS = {
    11, 12, 13,   # kiss (both/left/right)
    15,           # both hands up
    17,           # clap
    18,           # high five
    19,           # hug
    20, 21,       # heart (both/right)
    22,           # reject
    23,           # right hand up
    24,           # x-ray (ultraman ray)
    25,           # face wave
    26,           # high wave
    27,           # shake hand
    99,           # release arm
}

FSM_REGULAR = 501             # 팔 액션은 이 상태에서만 동작한다

# ── 판별 파라미터 ────────────────────────────────────────────────────
# 같은 자세가 이만큼 연속으로 잡혀야 인정한다. 순간적인 오검출을 거른다.
HOLD_FRAMES = 6
# 동작을 보낸 뒤 이만큼은 새 동작을 받지 않는다.
# G1 팔 액션이 3~8초 걸리므로 그보다 길게 잡는다.
ACTION_COOLDOWN = 8.0
# 관절이 이 신뢰도 미만이면 무시한다.
MIN_VIS = 0.6

# ── 키스 판별 ────────────────────────────────────────────────────────
# 손가락 관절이 없는 Pose 모델 특성상 "손 모양"은 못 본다. 대신
# 손목이 코(얼굴) 근처까지 오는 것을 뽀뽀 동작의 대체 신호로 쓴다.
# 흔들기/올림 판정보다 먼저 체크해서 우선순위를 준다 — 손이 얼굴
# 근처에 있으면 "손 든 것"으로 오판하지 않도록.
KISS_MAX_DIST = 0.12    # 정규화 좌표 기준, 손목-코 거리 이 이하면 "얼굴 근처"

# ── 흔들기 판별 (상태 기계 방식) ─────────────────────────────────────
# 손이 올라간 "순간"부터 타이머를 시작해서:
#   · 그 안에 유의미한 좌우 방향전환이 한 번이라도 감지되면 → 즉시 wave 로 확정
#   · UP_HOLD_SECONDS 동안 방향전환이 없으면 → still(그냥 든 상태) 로 확정
# 한 번 wave 로 확정되면 손을 내릴 때까지 그 상태를 유지한다 — 흔들다가
# 잠깐 멈췄다고 다시 "든 상태"로 되돌아가 버벅이지 않도록.
WAVE_MIN_DELTA = 0.02   # 노이즈 무시할 최소 이동량 (정규화 좌표 기준)
UP_HOLD_SECONDS = 2.0   # 이 시간 동안 방향전환 없으면 "든 상태(정지)"로 확정
MIN_UP_SAMPLES = 5      # 시간이 지나도 이만큼 프레임을 못 봤으면 still 확정을 미룬다
                        # (실기체 네트워크 스트림처럼 fps가 낮으면 1초 동안 샘플이
                        # 너무 적어서 방향전환을 잡을 기회도 없이 still로 확정되는 걸 방지)

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

# ── 손하트 판별 ──────────────────────────────────────────────────────
# 절대 거리 대신 "손 크기(손목~중지뿌리 거리)" 대비 비율로 판단해서
# 카메라와의 거리가 달라져도 안정적으로 동작하게 한다.
HEART_PINCH_RATIO = 0.35  # 엄지-검지 끝 거리 / 손 크기 — 이 이하면 "붙었다"
HEART_CURL_RATIO = 1.05   # 손가락끝-손목 거리 / 뿌리마디-손목 거리 — 이 이하면 "접혔다"


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
        # 방금 손이 올라간 순간 — 판정 시작
        state["phase"] = "pending"
        state["since"] = now
        state["extreme"] = wrist_x
        state["dir"] = None
        state["count"] = 1
        return "pending"

    if state["phase"] == "wave":
        return "wave"  # 이미 확정됨 — 손 내릴 때까지 유지

    state["count"] += 1

    # pending 또는 still — 계속 방향전환 감시 (still 확정 후에도 흔들면 바로 wave로 승격)
    delta = wrist_x - state["extreme"]
    if abs(delta) >= WAVE_MIN_DELTA:
        new_dir = 1 if delta > 0 else -1
        if state["dir"] is not None and new_dir != state["dir"]:
            state["phase"] = "wave"
            return "wave"
        state["dir"] = new_dir
        state["extreme"] = wrist_x

    # 시간과 샘플 수 둘 다 충족해야 still로 확정한다 — fps가 낮은 스트림에서
    # 표본이 부족한 채로 시간만 지났다고 성급하게 확정하지 않도록.
    if (state["phase"] == "pending"
            and (now - state["since"]) >= UP_HOLD_SECONDS
            and state["count"] >= MIN_UP_SAMPLES):
        state["phase"] = "still"

    return state["phase"]


def dist(a, b):
    """두 랜드마크 사이 유클리드 거리 (정규화 좌표 기준)."""
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5


DEBUG_HEART = False  # 콘솔에 손하트 판별 값 실시간 출력 (문제 생기면 True로)


def is_finger_heart(hand_landmarks, tag=""):
    """엄지-검지를 붙이고 나머지 손가락을 접은 '손가락 하트' 모양인지 판정.

    절대 거리 대신 손 크기(손목~중지뿌리마디 거리) 대비 비율로 계산해서
    카메라와의 거리가 달라져도 안정적으로 동작한다.
    """
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


def kiss_signal(lm, wrist_idx, hand_landmarks):
    """이 손이 뽀뽀 동작 중인지 판정.

    우선순위:
      1. Holistic 손 랜드마크가 잡히면 → 가운데 손가락 끝(HAND_MIDDLE_TIP)이
         입술(입 좌우 랜드마크 중점) 근처인지로 판정. 훨씬 정확하다.
      2. 손 랜드마크가 안 잡히면(가려짐, Holistic 미검출 등) → 손목이 코
         근처인지로 폴백. Pose 랜드마크만으로도 동작하는 안전망.
    """
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

    # 폴백: 손 랜드마크가 없으면 손목-코 거리로 대체
    if lm[wrist_idx].visibility < MIN_VIS or lm[NOSE].visibility < MIN_VIS:
        return False
    dx = lm[wrist_idx].x - lm[NOSE].x
    dy = lm[wrist_idx].y - lm[NOSE].y
    return (dx * dx + dy * dy) ** 0.5 <= KISS_MAX_DIST


def classify(lm, left_hand, right_hand, l_state, r_state, now):
    """관절 좌표에서 행동을 판별한다.

    MediaPipe 좌표계는 **y 가 아래로 갈수록 커진다.** 따라서
    "손이 어깨보다 위" = wrist.y < shoulder.y 다.

    좌우 주의: MediaPipe 의 LEFT/RIGHT 는 **사람 기준**이다.
    거울처럼 보이는 화면상의 좌우와 반대다. 여기서는 사람 기준을 따른다
    — 사람이 오른손을 들면 G1 도 오른손을 든다.

    left_hand/right_hand 는 Holistic 의 left_hand_landmarks/
    right_hand_landmarks (없으면 None — kiss_signal 이 폴백 처리).

    판정 우선순위: 키스(입 근처) > 손하트(손 모양) > 흔들기/올림.
    손이 입 근처에 있거나 손하트 모양일 때 "손 든 것"으로 오판하지
    않도록 먼저 체크한다. 이때 흔들기 상태 기계는 "내려간 것"으로
    리셋해서, 손이 이동하는 움직임이 나중에 엉뚱하게 wave로 튀지
    않게 한다.

    흔드는 것과 그냥 든 것은 update_wave_state 상태 기계로 구분한다
    (자세한 설명은 update_wave_state 참고).
    """
    def ok(i):
        return lm[i].visibility >= MIN_VIS

    if not (ok(L_SHOULDER) and ok(R_SHOULDER)):
        update_wave_state(now, False, 0.0, l_state)
        update_wave_state(now, False, 0.0, r_state)
        return None, "어깨가 안 보임"

    # ── 키스 판별 (최우선) ──────────────────────────────────────────
    l_kiss = kiss_signal(lm, L_WRIST, left_hand)
    r_kiss = kiss_signal(lm, R_WRIST, right_hand)

    if l_kiss or r_kiss:
        # 키스 동작 중엔 흔들기 상태 기계를 "내려간 것"으로 리셋해서
        # 손이 얼굴로 이동하는 움직임이 나중에 wave로 오판되지 않게 한다.
        update_wave_state(now, False, 0.0, l_state)
        update_wave_state(now, False, 0.0, r_state)
        if l_kiss and r_kiss:
            return "two_hand_kiss", "양손 키스"
        if r_kiss:
            return "right_kiss", "오른손 키스"
        return "left_kiss", "왼손 키스"

    # ── 손하트 판별 (키스 다음 우선순위) ─────────────────────────────
    # 어느 손이든 손가락 하트 모양이면 양손하트(two_hand_heart)로 통일.
    l_heart = is_finger_heart(left_hand, tag="L")
    r_heart = is_finger_heart(right_hand, tag="R")

    if l_heart or r_heart:
        update_wave_state(now, False, 0.0, l_state)
        update_wave_state(now, False, 0.0, r_state)
        return "two_hand_heart", "손하트"

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
        # 아직 흔드는지/가만히 있는지 판정 중 — 라벨을 None으로 둬서
        # main()의 held_n 카운트(=액션 발동 조건)가 시작되지 않게 한다.
        # still/wave 로 "확정"된 뒤에야 held_n 이 쌓이기 시작한다.
        return None, "오른손 올림 (판정 중…)"
    if l_phase == "pending":
        return None, "왼손 올림 (판정 중…)"

    return None, "대기"


ACTION_MAP = {
    "right_hand_up":   (ACTION_RIGHT_HAND_UP, "G1 오른손 올리기"),
    "right_hand_wave": (ACTION_WAVE,          "G1 오른손 흔들기"),
    # TODO: left_hand_up/left_hand_wave 는 아직 전용 액션 ID가 없어
    #       임시로 오른손 ID를 재사용 중. SDK 리스트에 추가되면 교체할 것.
    "left_hand_up":    (ACTION_RIGHT_HAND_UP, "G1 왼손 올리기 (임시: 오른손 ID 재사용)"),
    "left_hand_wave":  (ACTION_WAVE,          "G1 왼손 흔들기 (임시: WAVE ID 재사용)"),
    "both_hands_up":   (ACTION_BOTH_HANDS_UP, "G1 양팔 올리기"),
    "two_hand_kiss":   (ACTION_TWO_HAND_KISS, "G1 양손 뽀뽀"),
    "left_kiss":       (ACTION_LEFT_KISS,     "G1 왼손 뽀뽀"),
    "right_kiss":      (ACTION_RIGHT_KISS,    "G1 오른손 뽀뽀"),
    "two_hand_heart":  (ACTION_TWO_HAND_HEART, "G1 양손 하트"),
}


def main():
    ap = argparse.ArgumentParser(
        description="MediaPipe Pose 기반 사람 행동 인식 → G1 대응 동작")
    ap.add_argument("--source", default="http://192.168.123.164:8080/stream",
                    help="영상 입력. 웹캠은 0, 로봇은 MJPEG URL (기본)")
    ap.add_argument("--iface", help="예: enx... (CYCLONEDDS_URI 설정 시 생략 가능)")
    ap.add_argument("--domain", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true",
                    help="로봇에 명령을 보내지 않고 인식만 확인")
    ap.add_argument("--no-window", action="store_true",
                    help="화면 표시 없이 콘솔로만")
    args = ap.parse_args()

    try:
        import mediapipe as mp
    except ImportError:
        sys.exit("\n  mediapipe 가 없습니다:  pip install mediapipe opencv-python\n")

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

    # ── 영상 입력 ────────────────────────────────────────────────────
    src = int(args.source) if str(args.source).isdigit() else args.source
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        sys.exit(f"\n  영상을 열 수 없습니다: {args.source}\n"
                 "  · 로봇 카메라라면 Jetson 에서 g1_cam_server.py 가 떠 있는지\n"
                 "  · 웹캠이라면 --source 0\n")
    # 밀린 프레임을 쌓지 않는다 — 체감 지연을 줄이는 데 가장 효과가 크다
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    holistic = mp.solutions.holistic.Holistic(
        model_complexity=1,           # 0(빠름) 1(보통) 2(정확). 1이 무난하다
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
        refine_face_landmarks=False)  # 얼굴 468점 세밀화는 안 씀 — 속도 아끼기
    drawer = mp.solutions.drawing_utils
    style = mp.solutions.drawing_styles
    mp_holistic = mp.solutions.holistic

    print(f"\n  입력: {args.source}")
    print(f"  모드: {'인식만 (로봇에 명령 안 보냄)' if args.dry_run else '실전'}")
    print(f"  판정: 같은 자세 {HOLD_FRAMES}프레임 연속 → 동작 실행")
    print(f"        흔들기 판정: 든 순간부터 {UP_HOLD_SECONDS}초 안에 방향전환 있으면 즉시 흔듦")
    print(f"        실행 후 {ACTION_COOLDOWN}초 동안 새 동작 무시")
    print("\n  q 또는 Esc 로 종료\n")

    held, held_n = None, 0
    last_action_at = 0.0
    executing = ""

    # 손 하나씩의 흔들기 판별 상태 — 프레임마다 유지되어야 하므로 루프 밖에서 생성
    l_wave_state = new_wave_state()
    r_wave_state = new_wave_state()

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("  프레임 수신 실패 — 재시도")
                time.sleep(0.2)
                continue

            now = time.monotonic()

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            res = holistic.process(rgb)

            label, desc = (None, "사람 없음")
            if res.pose_landmarks:
                label, desc = classify(res.pose_landmarks.landmark,
                                        res.left_hand_landmarks, res.right_hand_landmarks,
                                        l_wave_state, r_wave_state, now)
            else:
                # 사람이 화면에서 사라지면 상태를 초기화해서, 다시 나타났을 때
                # 이전의 흔들림 상태와 이어붙여 오판하지 않도록 한다.
                update_wave_state(now, False, 0.0, l_wave_state)
                update_wave_state(now, False, 0.0, r_wave_state)

            # ── 같은 자세가 연속으로 유지되는지 ──────────────────────
            if label is not None and label == held:
                held_n += 1
            else:
                held, held_n = label, 1 if label else 0

            cooling = (now - last_action_at) < ACTION_COOLDOWN

            if (label and held_n == HOLD_FRAMES and not cooling):
                action_id, action_name = ACTION_MAP[label]
                print(f"  [{time.strftime('%H:%M:%S')}] {desc} → {action_name}")
                executing = action_name
                last_action_at = now
                if arm is not None:
                    if action_id not in ALLOWED_ACTION_IDS:
                        # 화이트리스트에 없는 ID — 절대 실행하지 않는다.
                        # (하체 오작동 방지용 이중 안전장치. ACTION_MAP 오타나
                        #  잘못된 값이 들어와도 여기서 막힌다.)
                        print(f"    [안전] 액션 ID {action_id} 는 화이트리스트에 없어 실행하지 않음")
                    else:
                        try:
                            arm.ExecuteAction(action_id)
                        except Exception as e:
                            print(f"    액션 실패: {e}")

            # ── 화면 ─────────────────────────────────────────────────
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

                bar = 40
                cv2.rectangle(frame, (0, 0), (frame.shape[1], bar), (0, 0, 0), -1)
                cv2.putText(frame, desc, (10, 27),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

                if label:
                    w = int(frame.shape[1] * min(held_n / HOLD_FRAMES, 1.0))
                    cv2.rectangle(frame, (0, bar), (w, bar + 5), (0, 200, 0), -1)

                if cooling:
                    left = ACTION_COOLDOWN - (now - last_action_at)
                    cv2.putText(frame, f"{executing}  ({left:.1f}s)",
                                (10, frame.shape[0] - 15),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2)

                cv2.imshow("G1 Pose Action", frame)
                if cv2.waitKey(1) & 0xFF in (ord('q'), 27):
                    break

    except KeyboardInterrupt:
        print("\n  중단")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        holistic.close()
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
