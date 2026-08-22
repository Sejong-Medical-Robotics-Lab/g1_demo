#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_cam_server.py — Jetson 에서 RealSense 영상을 MJPEG 로 흘려보낸다.

    [Jetson]  카메라 → JPEG 압축 → HTTP 스트림
                  ↓
    [PC]      영상 받아서 MediaPipe Pose → 행동 판별 → G1 팔 동작

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
왜 ROS 를 안 쓰나
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Jetson 은 ROS 2 Foxy(2020), PC 는 Jazzy(2024)다. 두 대를 같은 도메인에
두면 DDS 규약 차이로

    Deserialization of data failed → std::bad_alloc → 노드 사망

이 난다. 토픽 이름은 보이지만 실제 데이터는 오가지 못한다.

그래서 **HTTP 로 영상만 넘긴다.** MJPEG 는 JPEG 을 연달아 보내는 방식이라
구현이 단순하고, 브라우저로도 바로 열린다.

또 하나의 이유: **MediaPipe 는 Jetson(aarch64)에 설치하기 어렵다.**
공식 wheel 이 x86_64 와 라즈베리파이용뿐이라 Jetson 용은 커뮤니티 빌드를
쓰거나 Bazel 로 직접 빌드해야 한다. PC(x86_64)에서는 `pip install mediapipe`
한 줄이면 끝난다. **무거운 일은 PC 가 하고 Jetson 은 영상만 넘긴다.**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
준비 (Jetson, 한 번만)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    sudo apt install -y python3-opencv

인터넷이 필요하면 내장 WiFi 를 쓴다(유선은 로봇 내부망 전용):
    sudo nmcli device wifi connect "<SSID>" password "<PW>"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
실행 (Jetson)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    python3 g1_cam_server.py

    # 카메라 장치를 못 찾으면 번호를 지정
    python3 g1_cam_server.py --device 4
    python3 g1_cam_server.py --list      # 후보 나열

확인:
    PC 브라우저에서  http://192.168.123.164:8080

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RealSense 와 /dev/video*
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RealSense 는 UVC 장치라 `/dev/video0`, `video1`, ... 로 여러 개가 잡힌다.
**그중 하나만 컬러(RGB)이고 나머지는 깊이·적외선·메타데이터다.**
번호는 기기와 연결 순서에 따라 달라진다.

이 스크립트는 후보를 차례로 열어보고 **컬러 영상이 나오는 것을 자동으로
고른다.** 잘못 고르면 `--device` 로 직접 지정한다.
"""
import argparse
import socketserver
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import cv2

# ── 전역 상태 ────────────────────────────────────────────────────────
# 캡처 스레드가 최신 프레임만 여기에 덮어쓴다.
# 요청이 밀려도 항상 최신 것만 내보내므로 **지연이 쌓이지 않는다.**
_latest_jpeg = None
_lock = threading.Lock()
_running = True
_stat = {"grabbed": 0, "sent": 0, "fps": 0.0}


def find_color_device(max_index=10, want_w=640, want_h=480):
    """컬러 영상이 나오는 /dev/video* 를 찾는다.

    RealSense 는 여러 개의 video 노드를 만든다. 깊이·적외선 노드는
    흑백이거나 열리지 않으므로, 실제로 3채널 컬러 프레임이 나오는
    장치를 고른다.
    """
    print("  카메라 장치 탐색 중...")
    for idx in range(max_index):
        cap = cv2.VideoCapture(idx)
        if not cap.isOpened():
            cap.release()
            continue
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, want_w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, want_h)
        ok, frame = cap.read()
        if ok and frame is not None and frame.ndim == 3 and frame.shape[2] == 3:
            h, w = frame.shape[:2]
            # 흑백을 3채널로 복제한 경우(적외선)는 세 채널 값이 거의 같다.
            b, g, r = frame[:, :, 0], frame[:, :, 1], frame[:, :, 2]
            is_gray = (abs(int(b.mean()) - int(r.mean())) < 2 and
                       abs(int(g.mean()) - int(r.mean())) < 2)
            print(f"    /dev/video{idx}: {w}x{h} "
                  f"{'(흑백으로 보임 — 적외선?)' if is_gray else '컬러'}")
            if not is_gray:
                cap.release()
                return idx
        cap.release()
    return None


def capture_loop(device, width, height, fps, quality):
    global _latest_jpeg, _running

    cap = cv2.VideoCapture(device)
    if not cap.isOpened():
        sys.exit(f"\n  [실패] /dev/video{device} 를 열 수 없습니다.\n"
                 "  --list 로 후보를 확인하거나 카메라 연결을 점검하세요.")

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    # 드라이버 내부 버퍼를 1로 줄인다 — 오래된 프레임이 쌓이지 않게.
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    aw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    ah = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"\n  카메라 열림: /dev/video{device}  {aw}x{ah}")
    if (aw, ah) != (width, height):
        print(f"  (요청한 {width}x{height} 는 지원되지 않아 위 값으로 잡혔습니다)")

    params = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    t0, n = time.monotonic(), 0

    while _running:
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.05)
            continue

        ok, buf = cv2.imencode(".jpg", frame, params)
        if not ok:
            continue

        with _lock:
            _latest_jpeg = buf.tobytes()
        _stat["grabbed"] += 1

        n += 1
        dt = time.monotonic() - t0
        if dt >= 2.0:
            _stat["fps"] = n / dt
            t0, n = time.monotonic(), 0
            print(f"    캡처 {_stat['fps']:.1f} fps   "
                  f"전송 {_stat['sent']}   ", end="\r", flush=True)

    cap.release()


PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>G1 Camera</title>
<style>
 body{background:#1a1a1a;color:#ddd;font-family:sans-serif;margin:0;
      display:flex;flex-direction:column;align-items:center;padding:20px}
 img{max-width:100%;border:1px solid #444}
 p{color:#888;font-size:14px}
</style></head>
<body>
<h3>G1 RealSense</h3>
<img src="/stream">
<p>PC 에서 인식에 쓰려면: cv2.VideoCapture("http://&lt;JETSON_IP&gt;:8080/stream")</p>
</body></html>""".encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass          # 요청마다 찍히는 로그를 끈다

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)
            return

        if self.path != "/stream":
            self.send_error(404)
            return

        # ── MJPEG: JPEG 을 경계 문자열로 구분해 연달아 보낸다 ──────
        self.send_response(200)
        self.send_header("Age", "0")
        self.send_header("Cache-Control", "no-cache, private")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Type",
                         "multipart/x-mixed-replace; boundary=FRAME")
        self.end_headers()

        last = None
        try:
            while _running:
                with _lock:
                    jpg = _latest_jpeg
                if jpg is None or jpg is last:
                    time.sleep(0.005)
                    continue
                last = jpg
                self.wfile.write(b"--FRAME\r\n")
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(jpg)))
                self.end_headers()
                self.wfile.write(jpg)
                self.wfile.write(b"\r\n")
                _stat["sent"] += 1
        except (BrokenPipeError, ConnectionResetError):
            pass          # 클라이언트가 창을 닫은 것. 정상이다.


class ThreadedHTTP(socketserver.ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    global _running

    ap = argparse.ArgumentParser(description="RealSense → MJPEG 스트리밍")
    ap.add_argument("--device", type=int, default=None,
                    help="/dev/videoN 의 N. 생략하면 컬러 장치를 자동 탐색")
    ap.add_argument("--list", action="store_true",
                    help="사용 가능한 카메라 장치를 나열만 하고 종료")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--fps", type=int, default=15)
    ap.add_argument("--quality", type=int, default=70,
                    help="JPEG 품질 1~100. 낮출수록 전송이 빠르다 (기본 70)")
    args = ap.parse_args()

    if args.list:
        find_color_device()
        return

    device = args.device
    if device is None:
        device = find_color_device(want_w=args.width, want_h=args.height)
        if device is None:
            sys.exit("\n  [실패] 컬러 카메라를 찾지 못했습니다.\n"
                     "  ls /dev/video* 로 장치를 확인하고 --device 로 지정하세요.")

    th = threading.Thread(
        target=capture_loop,
        args=(device, args.width, args.height, args.fps, args.quality),
        daemon=True)
    th.start()

    # 첫 프레임이 들어올 때까지 잠깐 기다린다
    for _ in range(50):
        with _lock:
            if _latest_jpeg is not None:
                break
        time.sleep(0.1)

    srv = ThreadedHTTP(("0.0.0.0", args.port), Handler)
    print(f"\n  스트리밍 시작 — 포트 {args.port}")
    print(f"    브라우저    http://<Jetson_IP>:{args.port}")
    print(f"    PC 코드에서 cv2.VideoCapture(\"http://192.168.123.164:{args.port}/stream\")")
    print("\n  Ctrl+C 로 종료\n")

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  종료 중...")
    finally:
        _running = False
        srv.shutdown()
        time.sleep(0.3)
        print("  종료 완료")


if __name__ == "__main__":
    main()
