#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
g1_rgbd_server.py
-----------------
G1 내부 Jetson에서 RealSense D435i의 RGB + Depth를 동시에 읽는다.

기존 g1_cam_server.py와 다른 점

1) RGB 영상은 기존처럼 MJPEG /stream 으로 보낸다.

2) Depth는 전체 영상을 전송하지 않고,
   PC가 요청한 RGB 픽셀 (x, y)의 실제 거리(m)만 JSON으로 돌려준다.

3) Depth는 color 좌표계에서 MediaPipe RGB 좌표와 바로 대응시킨다.

구조
    RealSense D435i
       ├─ RGB ──> JPEG ──> HTTP /stream
       └─ Depth ─> color align ─> HTTP /depth?x=320&y=240

"""

import argparse
import json
import socketserver
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

import cv2
import numpy as np

try:
    import pyrealsense2 as rs
except ImportError:
    raise SystemExit(
        "\n[실패] pyrealsense2가 없습니다.\n"
        "Jetson에서 librealsense Python binding 설치 여부를 먼저 확인하세요.\n"
        "확인: python3 -c \"import pyrealsense2 as rs; print('OK')\"\n"
    )


_latest_jpeg = None
_latest_depth = None          # color 좌표계에 align된 uint16 depth image
_depth_scale = None           # raw depth 1 unit이 몇 meter인지
_lock = threading.Lock()
_running = True

_stats = {
    "frames": 0,
    "fps": 0.0,
    "width": 0,
    "height": 0,
}


def start_realsense(width, height, fps):
    """RealSense RGB + Depth pipeline을 시작한다."""
    pipeline = rs.pipeline()
    config = rs.config()

    config.enable_stream(
        rs.stream.depth,
        width, height,
        rs.format.z16,
        fps
    )
    config.enable_stream(
        rs.stream.color,
        width, height,
        rs.format.bgr8,
        fps
    )

    print(f"[RealSense] 시작 요청: {width}x{height} @ {fps} fps")
    profile = pipeline.start(config)

    depth_sensor = profile.get_device().first_depth_sensor()
    depth_scale = depth_sensor.get_depth_scale()

    # Depth를 RGB 좌표계에 맞춘다.
    align = rs.align(rs.stream.color)

    print(f"[RealSense] depth scale = {depth_scale:.8f} m/unit")
    return pipeline, align, depth_scale


def capture_loop(width, height, fps, quality):
    """RGB/Depth 최신 프레임을 계속 갱신한다."""
    global _latest_jpeg, _latest_depth, _depth_scale, _running

    pipeline = None

    try:
        pipeline, align, depth_scale = start_realsense(width, height, fps)
        _depth_scale = depth_scale

        jpeg_params = [int(cv2.IMWRITE_JPEG_QUALITY), quality]

        t0 = time.monotonic()
        n = 0

        while _running:
            frames = pipeline.wait_for_frames(timeout_ms=3000)

            # depth를 color 좌표에 정렬
            aligned = align.process(frames)

            color_frame = aligned.get_color_frame()
            depth_frame = aligned.get_depth_frame()

            if not color_frame or not depth_frame:
                continue

            color = np.asanyarray(color_frame.get_data())
            depth = np.asanyarray(depth_frame.get_data()).copy()

            ok, buf = cv2.imencode(".jpg", color, jpeg_params)
            if not ok:
                continue

            with _lock:
                _latest_jpeg = buf.tobytes()
                _latest_depth = depth

            _stats["frames"] += 1
            _stats["height"], _stats["width"] = depth.shape[:2]

            n += 1
            dt = time.monotonic() - t0
            if dt >= 2.0:
                _stats["fps"] = n / dt
                print(
                    f"[RealSense] {_stats['fps']:.1f} fps "
                    f"({_stats['width']}x{_stats['height']})",
                    end="\r",
                    flush=True
                )
                t0 = time.monotonic()
                n = 0

    except Exception as e:
        print(f"\n[RealSense 오류] {e}")
        _running = False

    finally:
        if pipeline is not None:
            try:
                pipeline.stop()
            except Exception:
                pass


def get_distance(x, y, radius=3):
    """
    (x, y) 주변의 depth 값을 모아 median 거리(m)를 반환한다.

    픽셀 하나만 읽으면 0값/노이즈에 민감하므로
    기본 7x7 영역(radius=3)의 유효값 median을 사용한다.
    """
    with _lock:
        if _latest_depth is None or _depth_scale is None:
            return None, 0

        depth = _latest_depth
        scale = _depth_scale

        h, w = depth.shape[:2]

        if x < 0 or x >= w or y < 0 or y >= h:
            return None, 0

        x1 = max(0, x - radius)
        x2 = min(w, x + radius + 1)
        y1 = max(0, y - radius)
        y2 = min(h, y + radius + 1)

        roi = depth[y1:y2, x1:x2].astype(np.float32)

    # 0은 RealSense에서 invalid depth
    valid = roi[roi > 0]

    if valid.size == 0:
        return None, 0

    distance_m = float(np.median(valid) * scale)
    return distance_m, int(valid.size)


PAGE = b"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>G1 RGB-D Camera</title>
<style>
body {
  background:#171717; color:#ddd; font-family:sans-serif;
  display:flex; flex-direction:column; align-items:center;
}
img { max-width:95%; border:1px solid #555; }
code { color:#8fd3ff; }
</style>
</head>
<body>
<h3>G1 RealSense RGB-D</h3>
<img src="/stream">
<p>Depth API example:
<code>/depth?x=320&y=240</code></p>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send_json(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)
            return

        if parsed.path == "/status":
            self._send_json({
                "ok": _latest_jpeg is not None and _latest_depth is not None,
                "fps": round(_stats["fps"], 2),
                "width": _stats["width"],
                "height": _stats["height"],
            })
            return

        if parsed.path == "/depth":
            qs = parse_qs(parsed.query)

            try:
                x = int(qs["x"][0])
                y = int(qs["y"][0])
                radius = int(qs.get("radius", ["3"])[0])
                radius = max(0, min(radius, 10))
            except (KeyError, ValueError):
                self._send_json(
                    {"ok": False, "error": "use /depth?x=320&y=240"},
                    status=400
                )
                return

            distance_m, valid_pixels = get_distance(x, y, radius)

            if distance_m is None:
                self._send_json({
                    "ok": False,
                    "x": x,
                    "y": y,
                    "distance_m": None,
                    "valid_pixels": valid_pixels
                })
            else:
                self._send_json({
                    "ok": True,
                    "x": x,
                    "y": y,
                    "distance_m": round(distance_m, 3),
                    "valid_pixels": valid_pixels
                })
            return

        if parsed.path == "/stream":
            self.send_response(200)
            self.send_header("Age", "0")
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Pragma", "no-cache")
            self.send_header(
                "Content-Type",
                "multipart/x-mixed-replace; boundary=FRAME"
            )
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

            except (BrokenPipeError, ConnectionResetError):
                pass

            return

        self.send_error(404)


class ThreadedHTTP(socketserver.ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    global _running

    ap = argparse.ArgumentParser(
        description="G1 RealSense RGB + Depth HTTP server"
    )
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--fps", type=int, default=15)
    ap.add_argument("--quality", type=int, default=70)
    args = ap.parse_args()

    th = threading.Thread(
        target=capture_loop,
        args=(args.width, args.height, args.fps, args.quality),
        daemon=True
    )
    th.start()

    # 첫 RGB + Depth 프레임 대기
    for _ in range(80):
        with _lock:
            ready = _latest_jpeg is not None and _latest_depth is not None
        if ready:
            break
        if not _running:
            break
        time.sleep(0.1)

    if not _running:
        raise SystemExit("\n[실패] RealSense pipeline 시작에 실패했습니다.")

    server = ThreadedHTTP(("0.0.0.0", args.port), Handler)

    print("\nG1 RGB-D 서버 시작")
    print(f"  영상  : http://192.168.123.164:{args.port}/stream")
    print(f"  거리  : http://192.168.123.164:{args.port}/depth?x=320&y=240")
    print(f"  상태  : http://192.168.123.164:{args.port}/status")
    print("\nCtrl+C 로 종료\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n종료 중...")
    finally:
        _running = False
        server.shutdown()
        time.sleep(0.3)
        print("종료 완료")


if __name__ == "__main__":
    main()
