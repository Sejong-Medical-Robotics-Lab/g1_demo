#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
g1_person_distance.py
---------------------
PC에서 G1의 MJPEG 영상을 받아 MediaPipe Holistic으로 사람 몸 중심을 찾고,
Jetson의 /depth API에 해당 픽셀의 실제 거리(m)를 요청해 화면에 표시
(로봇에 어떤 Action도 보내지 않는다)

구조
    MJPEG RGB
       ↓
    MediaPipe Holistic
       ↓
    어깨/골반 기반 몸통 중심 픽셀
       ↓
    GET /depth?x=...&y=...
       ↓
    실제 거리(m)
"""

import argparse
import json
import time
from urllib.request import urlopen
from urllib.error import URLError

import cv2

try:
    import mediapipe as mp
except ImportError:
    raise SystemExit(
        "\nmediapipe가 없습니다.\n"
        "설치: pip install mediapipe opencv-python\n"
    )


# MediaPipe Pose landmark 번호
L_SHOULDER = 11
R_SHOULDER = 12
L_HIP = 23
R_HIP = 24

MIN_VIS = 0.6


def visible(lm, idx):
    return lm[idx].visibility >= MIN_VIS


def get_body_center(lm):
    """
    몸통 중앙 좌표(normalized 0~1)를 구한다.

    1순위: 양 어깨 중심 + 양 골반 중심의 중간점
    2순위: 골반이 안 보이면 양 어깨 중심
    """
    if not (visible(lm, L_SHOULDER) and visible(lm, R_SHOULDER)):
        return None

    shoulder_x = (lm[L_SHOULDER].x + lm[R_SHOULDER].x) / 2.0
    shoulder_y = (lm[L_SHOULDER].y + lm[R_SHOULDER].y) / 2.0

    hips_ok = visible(lm, L_HIP) and visible(lm, R_HIP)

    if hips_ok:
        hip_x = (lm[L_HIP].x + lm[R_HIP].x) / 2.0
        hip_y = (lm[L_HIP].y + lm[R_HIP].y) / 2.0

        center_x = (shoulder_x + hip_x) / 2.0
        center_y = (shoulder_y + hip_y) / 2.0
    else:
        center_x = shoulder_x
        center_y = shoulder_y

    # 화면 밖으로 약간 튀는 경우 방지
    center_x = max(0.0, min(1.0, center_x))
    center_y = max(0.0, min(1.0, center_y))

    return center_x, center_y


def request_depth(base_url, x, y, radius=3, timeout=0.3):
    url = f"{base_url}/depth?x={x}&y={y}&radius={radius}"

    try:
        with urlopen(url, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))

        if data.get("ok") and data.get("distance_m") is not None:
            return float(data["distance_m"])

    except (URLError, TimeoutError, ValueError, OSError):
        pass

    return None


def distance_state(distance_m):
    """
    테스트용 상태 표시.
    아직 로봇 Action과 연결하지 않는다.
    """
    if distance_m is None:
        return "NO DEPTH", (0, 0, 255)

    if distance_m < 1.0:
        return "TOO CLOSE", (0, 0, 255)

    if distance_m <= 3.0:
        return "OK", (0, 255, 0)

    return "TOO FAR", (0, 180, 255)


def main():
    ap = argparse.ArgumentParser(
        description="MediaPipe 사람 중심 + RealSense Depth 거리 표시"
    )

    ap.add_argument(
        "--source",
        default="http://192.168.123.164:8080/stream",
        help="MJPEG URL 또는 웹캠 번호"
    )

    ap.add_argument(
        "--depth-base",
        default="http://192.168.123.164:8080",
        help="Jetson RGB-D server base URL"
    )

    ap.add_argument(
        "--query-hz",
        type=float,
        default=5.0,
        help="Depth API 요청 주기 (기본 5 Hz)"
    )

    ap.add_argument(
        "--radius",
        type=int,
        default=3,
        help="Depth median 영역 반경. 3이면 7x7"
    )

    args = ap.parse_args()

    src = int(args.source) if str(args.source).isdigit() else args.source

    cap = cv2.VideoCapture(src)

    if not cap.isOpened():
        raise SystemExit(
            f"\n영상을 열 수 없습니다: {args.source}\n"
            "Jetson에서 g1_rgbd_server.py가 실행 중인지 확인하세요.\n"
        )

    # 밀린 MJPEG 프레임을 최대한 줄임
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    holistic = mp.solutions.holistic.Holistic(
        model_complexity=1,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
        refine_face_landmarks=False
    )

    drawer = mp.solutions.drawing_utils
    styles = mp.solutions.drawing_styles
    mp_holistic = mp.solutions.holistic

    last_query = 0.0
    last_distance = None
    last_center_px = None

    query_period = 1.0 / max(args.query_hz, 0.1)

    print("\nG1 Person Distance")
    print(f"RGB   : {args.source}")
    print(f"Depth : {args.depth_base}/depth")
    print("q 또는 Esc로 종료\n")

    try:
        while True:
            ok, frame = cap.read()

            if not ok:
                print("프레임 수신 실패 - 재시도")
                time.sleep(0.2)
                continue

            h, w = frame.shape[:2]

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            res = holistic.process(rgb)

            center_px = None

            if res.pose_landmarks:
                lm = res.pose_landmarks.landmark
                center = get_body_center(lm)

                if center is not None:
                    cx, cy = center
                    px = int(cx * (w - 1))
                    py = int(cy * (h - 1))
                    center_px = (px, py)

            now = time.monotonic()

            # 네트워크 요청은 영상 프레임마다 하지 않고 기본 5 Hz만
            if (
                center_px is not None
                and now - last_query >= query_period
            ):
                px, py = center_px

                last_distance = request_depth(
                    args.depth_base,
                    px, py,
                    radius=args.radius
                )

                last_center_px = center_px
                last_query = now

            # ── 화면 표시 ──────────────────────────────────────────
            if res.pose_landmarks:
                drawer.draw_landmarks(
                    frame,
                    res.pose_landmarks,
                    mp_holistic.POSE_CONNECTIONS,
                    landmark_drawing_spec=
                        styles.get_default_pose_landmarks_style()
                )

            if center_px is not None:
                px, py = center_px
                cv2.circle(frame, (px, py), 8, (255, 0, 255), -1)
                cv2.circle(frame, (px, py), 14, (255, 255, 255), 2)

            state, state_color = distance_state(last_distance)

            # 상단 검은 바
            cv2.rectangle(frame, (0, 0), (w, 75), (0, 0, 0), -1)

            if last_distance is None:
                distance_text = "DISTANCE: --"
            else:
                distance_text = f"DISTANCE: {last_distance:.2f} m"

            cv2.putText(
                frame,
                distance_text,
                (12, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                (255, 255, 255),
                2
            )

            cv2.putText(
                frame,
                state,
                (12, 62),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                state_color,
                2
            )

            cv2.imshow("G1 Person Distance", frame)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break

    except KeyboardInterrupt:
        pass

    finally:
        cap.release()
        holistic.close()
        cv2.destroyAllWindows()
        print("\n종료")


if __name__ == "__main__":
    main()
