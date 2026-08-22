#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_pose_action.py — 사람 자세를 인식해 G1 의 대응 동작을 실행한다.

시나리오 4단계. **모방이 아니라 대응**이다 — 사람의 관절 각도를 실시간으로
로봇 관절에 복사하는 것이 아니라, 미리 정한 몇 가지 행동을 판별해서
그에 맞는 G1 의 사전 정의 동작을 실행한다.

    카메라 → MediaPipe Pose → 관절 좌표 → 행동 판별 → G1 팔 액션

    사람이 오른손을 올림  →  right_hand_up   (액션 23)
    사람이 왼손을 흔듦    →  wave_above_head (액션 26)
    사람이 양손을 올림    →  both_hands_up   (액션 15)

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

# ── G1 팔 액션 ID (SDK_API.md 참고, 실기체 확인값) ───────────────────
ACTION_RIGHT_HAND_UP = 23     # right_hand_up
ACTION_WAVE = 26              # wave_above_head
ACTION_BOTH_HANDS_UP = 15     # both_hands_up
ACTION_RELEASE = 99           # release arm

FSM_REGULAR = 501             # 팔 액션은 이 상태에서만 동작한다

# ── 판별 파라미터 ────────────────────────────────────────────────────
# 같은 자세가 이만큼 연속으로 잡혀야 인정한다. 순간적인 오검출을 거른다.
HOLD_FRAMES = 6
# 동작을 보낸 뒤 이만큼은 새 동작을 받지 않는다.
# G1 팔 액션이 3~8초 걸리므로 그보다 길게 잡는다.
ACTION_COOLDOWN = 8.0
# 관절이 이 신뢰도 미만이면 무시한다.
MIN_VIS = 0.6

# MediaPipe Pose 랜드마크 번호
L_SHOULDER, R_SHOULDER = 11, 12
L_ELBOW, R_ELBOW = 13, 14
L_WRIST, R_WRIST = 15, 16


def classify(lm):
    """관절 좌표에서 행동을 판별한다.

    MediaPipe 좌표계는 **y 가 아래로 갈수록 커진다.** 따라서
    "손이 어깨보다 위" = wrist.y < shoulder.y 다.

    좌우 주의: MediaPipe 의 LEFT/RIGHT 는 **사람 기준**이다.
    거울처럼 보이는 화면상의 좌우와 반대다. 여기서는 사람 기준을 따른다
    — 사람이 오른손을 들면 G1 도 오른손을 든다.
    """
    def ok(i):
        return lm[i].visibility >= MIN_VIS

    if not (ok(L_SHOULDER) and ok(R_SHOULDER)):
        return None, "어깨가 안 보임"

    sh_y = (lm[L_SHOULDER].y + lm[R_SHOULDER].y) / 2

    l_up = ok(L_WRIST) and lm[L_WRIST].y < sh_y
    r_up = ok(R_WRIST) and lm[R_WRIST].y < sh_y

    if l_up and r_up:
        return "both_hands_up", "양손 올림"
    if r_up:
        return "right_hand_up", "오른손 올림"
    if l_up:
        # 시나리오상 왼손은 "흔드는" 동작이지만, 흔드는 움직임을
        # 판별하려면 시간에 따른 손목 이동을 봐야 한다.
        # 여기서는 "왼손을 든 상태"로 단순화했다.
        # 필요하면 wrist.x 의 좌우 진동을 추가로 검사한다.
        return "left_hand_wave", "왼손 올림/흔듦"

    return None, "대기"


ACTION_MAP = {
    "right_hand_up":  (ACTION_RIGHT_HAND_UP,  "G1 오른손 올리기"),
    "left_hand_wave": (ACTION_WAVE,           "G1 손 흔들기"),
    "both_hands_up":  (ACTION_BOTH_HANDS_UP,  "G1 양팔 올리기"),
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

    pose = mp.solutions.pose.Pose(
        model_complexity=1,           # 0(빠름) 1(보통) 2(정확). 1이 무난하다
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5)
    drawer = mp.solutions.drawing_utils
    style = mp.solutions.drawing_styles

    print(f"\n  입력: {args.source}")
    print(f"  모드: {'인식만 (로봇에 명령 안 보냄)' if args.dry_run else '실전'}")
    print(f"  판정: 같은 자세 {HOLD_FRAMES}프레임 연속 → 동작 실행")
    print(f"        실행 후 {ACTION_COOLDOWN}초 동안 새 동작 무시")
    print("\n  q 또는 Esc 로 종료\n")

    held, held_n = None, 0
    last_action_at = 0.0
    executing = ""

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("  프레임 수신 실패 — 재시도")
                time.sleep(0.2)
                continue

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            res = pose.process(rgb)

            label, desc = (None, "사람 없음")
            if res.pose_landmarks:
                label, desc = classify(res.pose_landmarks.landmark)

            # ── 같은 자세가 연속으로 유지되는지 ──────────────────────
            if label is not None and label == held:
                held_n += 1
            else:
                held, held_n = label, 1 if label else 0

            now = time.monotonic()
            cooling = (now - last_action_at) < ACTION_COOLDOWN

            if (label and held_n == HOLD_FRAMES and not cooling):
                action_id, action_name = ACTION_MAP[label]
                print(f"  [{time.strftime('%H:%M:%S')}] {desc} → {action_name}")
                executing = action_name
                last_action_at = now
                if arm is not None:
                    try:
                        arm.ExecuteAction(action_id)
                    except Exception as e:
                        print(f"    액션 실패: {e}")

            # ── 화면 ─────────────────────────────────────────────────
            if not args.no_window:
                if res.pose_landmarks:
                    drawer.draw_landmarks(
                        frame, res.pose_landmarks,
                        mp.solutions.pose.POSE_CONNECTIONS,
                        landmark_drawing_spec=style.get_default_pose_landmarks_style())

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
        pose.close()
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
