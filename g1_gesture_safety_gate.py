#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import time
import cv2

try:
    import mediapipe as mp
except ImportError:
    raise SystemExit("mediapipe가 없습니다. 테스트 venv를 활성화하세요.")

import g1_pose_action as pose_action
from g1_person_distance import get_body_center, request_depth


def safety_check(distance_m, min_distance):
    if distance_m is None:
        return False, "NO DEPTH"
    if distance_m < min_distance:
        return False, "TOO CLOSE"
    return True, "SAFE"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="http://192.168.123.164:8080/stream")
    ap.add_argument("--depth-base", default="http://192.168.123.164:8080")
    ap.add_argument("--min-distance", type=float, default=1.0)
    ap.add_argument("--query-hz", type=float, default=5.0)
    ap.add_argument("--radius", type=int, default=3)
    args = ap.parse_args()

    src = int(args.source) if str(args.source).isdigit() else args.source
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        raise SystemExit("영상을 열 수 없습니다. Jetson RGB-D 서버를 확인하세요.")

    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    holistic = mp.solutions.holistic.Holistic(
        model_complexity=1,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
        refine_face_landmarks=False,
    )

    drawer = mp.solutions.drawing_utils
    styles = mp.solutions.drawing_styles
    mp_holistic = mp.solutions.holistic

    l_wave_state = pose_action.new_wave_state()
    r_wave_state = pose_action.new_wave_state()

    held = None
    held_n = 0
    last_depth_query = 0.0
    last_distance = None
    query_period = 1.0 / max(args.query_hz, 0.1)

    last_event = None
    last_event_time = 0.0
    event_cooldown = 1.5

    print("\n=== G1 Gesture + Distance Safety Gate ===")
    print("실제 G1 Action은 보내지 않습니다.")
    print(f"안전거리 기준: {args.min_distance:.2f} m")
    print("거리 < 기준  -> BLOCKED")
    print("거리 >= 기준 -> ALLOWED")
    print("q 또는 Esc로 종료\n")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.2)
                continue

            now = time.monotonic()
            h, w = frame.shape[:2]

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            res = holistic.process(rgb)

            label = None
            desc = "사람 없음"
            center_px = None

            if res.pose_landmarks:
                lm = res.pose_landmarks.landmark
                label, desc = pose_action.classify(
                    lm,
                    res.left_hand_landmarks,
                    res.right_hand_landmarks,
                    l_wave_state,
                    r_wave_state,
                    now,
                )

                center = get_body_center(lm)
                if center is not None:
                    cx, cy = center
                    center_px = (int(cx * (w - 1)), int(cy * (h - 1)))
            else:
                pose_action.update_wave_state(now, False, 0.0, l_wave_state)
                pose_action.update_wave_state(now, False, 0.0, r_wave_state)

            if center_px is not None and now - last_depth_query >= query_period:
                px, py = center_px
                last_distance = request_depth(
                    args.depth_base, px, py, radius=args.radius
                )
                last_depth_query = now

            if label is not None and label == held:
                held_n += 1
            else:
                held = label
                held_n = 1 if label else 0

            stable_gesture = (
                label is not None and held_n >= pose_action.HOLD_FRAMES
            )

            allowed, reason = safety_check(last_distance, args.min_distance)

            if stable_gesture:
                decision = "ALLOWED" if allowed else "BLOCKED"
                event = (label, decision)
                if event != last_event or now - last_event_time >= event_cooldown:
                    dtext = "--" if last_distance is None else f"{last_distance:.2f} m"
                    print(
                        f"[{time.strftime('%H:%M:%S')}] "
                        f"{desc} | distance={dtext} | {decision} ({reason})"
                    )
                    last_event = event
                    last_event_time = now

            if res.pose_landmarks:
                drawer.draw_landmarks(
                    frame,
                    res.pose_landmarks,
                    mp_holistic.POSE_CONNECTIONS,
                    landmark_drawing_spec=styles.get_default_pose_landmarks_style(),
                )
            if res.left_hand_landmarks:
                drawer.draw_landmarks(
                    frame, res.left_hand_landmarks, mp_holistic.HAND_CONNECTIONS
                )
            if res.right_hand_landmarks:
                drawer.draw_landmarks(
                    frame, res.right_hand_landmarks, mp_holistic.HAND_CONNECTIONS
                )

            if center_px is not None:
                px, py = center_px
                cv2.circle(frame, (px, py), 8, (255, 0, 255), -1)
                cv2.circle(frame, (px, py), 14, (255, 255, 255), 2)

            cv2.rectangle(frame, (0, 0), (w, 150), (0, 0, 0), -1)

            dtext = "DISTANCE: --" if last_distance is None else f"DISTANCE: {last_distance:.2f} m"
            cv2.putText(frame, dtext, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (255,255,255), 2)

            gtext = f"GESTURE: {label}" if label else "GESTURE: NONE"
            cv2.putText(frame, gtext, (12, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.66, (0,255,255), 2)

            scolor = (0,255,0) if allowed else (0,0,255)
            cv2.putText(frame, f"SAFETY: {reason}", (12, 96), cv2.FONT_HERSHEY_SIMPLEX, 0.70, scolor, 2)

            if stable_gesture:
                atext = "ACTION: ALLOWED" if allowed else "ACTION: BLOCKED"
                acolor = scolor
            else:
                atext = f"ACTION: WAITING ({held_n}/{pose_action.HOLD_FRAMES})"
                acolor = (255,255,255)

            cv2.putText(frame, atext, (12, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.68, acolor, 2)

            cv2.imshow("G1 Gesture Safety Gate - DRY RUN", frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break

    finally:
        cap.release()
        holistic.close()
        cv2.destroyAllWindows()
        print("\n종료")


if __name__ == "__main__":
    main()
