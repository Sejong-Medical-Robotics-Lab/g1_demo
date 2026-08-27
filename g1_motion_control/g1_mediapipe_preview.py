#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_mediapipe_preview.py — 웹캠으로 MediaPipe Holistic 뼈대만 띄워본다.
로직 없음. 그냥 자세/양손 인식이 눈으로 잘 되는지 확인용.

실행:
    python3 g1_mediapipe_preview.py                # 자세+양손 다
    python3 g1_mediapipe_preview.py --mode hands    # 손만
    python3 g1_mediapipe_preview.py --mode pose     # 스켈레톤(자세)만
    q 또는 Esc 로 종료
"""
import argparse

import cv2
import mediapipe as mp

ap = argparse.ArgumentParser()
ap.add_argument("--mode", choices=["both", "hands", "pose"], default="both",
                help="both: 자세+손 다 표시 / hands: 손만 / pose: 스켈레톤(자세)만")
args = ap.parse_args()

show_pose = args.mode in ("both", "pose")
show_hands = args.mode in ("both", "hands")

mp_holistic = mp.solutions.holistic
drawer = mp.solutions.drawing_utils
style = mp.solutions.drawing_styles

cap = cv2.VideoCapture(0)
if not cap.isOpened():
    raise SystemExit("웹캠을 열 수 없습니다.")

with mp_holistic.Holistic(
        model_complexity=1,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
        refine_face_landmarks=False) as holistic:

    while True:
        ok, frame = cap.read()
        if not ok:
            continue

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        res = holistic.process(rgb)

        if show_pose and res.pose_landmarks:
            drawer.draw_landmarks(
                frame, res.pose_landmarks, mp_holistic.POSE_CONNECTIONS,
                landmark_drawing_spec=style.get_default_pose_landmarks_style())
        if show_hands and res.left_hand_landmarks:
            drawer.draw_landmarks(frame, res.left_hand_landmarks, mp_holistic.HAND_CONNECTIONS)
        if show_hands and res.right_hand_landmarks:
            drawer.draw_landmarks(frame, res.right_hand_landmarks, mp_holistic.HAND_CONNECTIONS)

        cv2.imshow("MediaPipe Preview", frame)
        if cv2.waitKey(1) & 0xFF in (ord('q'), 27):
            break

cap.release()
cv2.destroyAllWindows()
