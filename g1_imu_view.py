#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_imu_view.py — G1 내장 IMU 실시간 확인 (읽기 전용).

IMU 는 G1 자체 센서 중 유일하게 '지금 당장' 볼 수 있는 것이다.
LiDAR/깊이 카메라와 달리 ROS 2 나 드라이버 설치 없이 rt/lowstate 에 이미 들어온다.
1~4단계 내내 기립 안정성·보행 흔들림을 보는 데 그대로 쓴다.

  LowState_.imu_state = { quaternion[4], gyroscope[3], accelerometer[3],
                          rpy[3], temperature }

이 스크립트는 로봇에 어떤 명령도 보내지 않는다.

사용:
  python3 g1_imu_view.py --iface enp2s0
  python3 g1_imu_view.py --iface enp2s0 --csv imu_walk_test.csv   # 기록
"""
import argparse
import datetime as _dt
import math
import sys
import time


class Buf:
    def __init__(self):
        self.msg = None
        self.stamp = 0.0
        self.count = 0

    def cb(self, msg):
        self.msg = msg
        self.stamp = time.time()
        self.count += 1


def main():
    ap = argparse.ArgumentParser(description="G1 내장 IMU 뷰어 (읽기 전용)")
    ap.add_argument("--iface", required=True, help="예: enp2s0")
    ap.add_argument("--domain", type=int, default=0)
    ap.add_argument("--hz", type=float, default=10.0, help="화면 갱신 [Hz]")
    ap.add_argument("--csv", help="기록 파일 경로 (미지정 시 기록 안 함)")
    args = ap.parse_args()

    try:
        from unitree_sdk2py.core.channel import (ChannelFactoryInitialize,
                                                 ChannelSubscriber)
        from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowState_
    except ImportError as e:
        sys.exit("unitree_sdk2py 를 찾을 수 없습니다 — venv 활성화 확인.\n"
                 "  cd ~/unitree_sdk2_python && source .venv/bin/activate\n"
                 f"(원인: {e})")

    ChannelFactoryInitialize(args.domain, args.iface)
    buf = Buf()
    sub = ChannelSubscriber("rt/lowstate", LowState_)
    sub.Init(buf.cb, 10)

    t0 = time.time()
    while buf.msg is None and time.time() - t0 < 4.0:
        time.sleep(0.05)
    if buf.msg is None:
        sys.exit("[실패] rt/lowstate 미수신 — 확인 순서: ① 로봇 전원 ② 유선 연결·"
                 "PC IP(192.168.123.x) ③ --iface 이름(ip addr) ④ --domain(실기체 0)")

    # 수신 주파수 측정
    c0, tm = buf.count, time.time()
    time.sleep(1.0)
    hz = (buf.count - c0) / max(time.time() - tm, 1e-6)
    print(f"\n  rt/lowstate 수신 {hz:.0f} Hz — Ctrl+C 로 종료\n")

    f = None
    if args.csv:
        f = open(args.csv, "w", encoding="utf-8")
        f.write("t,tick,roll_deg,pitch_deg,yaw_deg,"
                "gx,gy,gz,ax,ay,az,imu_temp\n")
        print(f"  기록 → {args.csv}\n")

    print(f"  {'roll':>8s} {'pitch':>8s} {'yaw':>8s} | "
          f"{'|gyro|':>7s} {'|accel|':>8s} | temp")
    t_start = time.time()
    period = 1.0 / max(args.hz, 0.5)
    try:
        while True:
            if time.time() - buf.stamp > 0.5:
                print("  [끊김] lowstate 수신 없음 — 연결 확인          ", end="\r")
                time.sleep(0.1)
                continue
            m = buf.msg
            imu = m.imu_state
            r, p, y = (math.degrees(float(v)) for v in imu.rpy)
            g = [float(v) for v in imu.gyroscope]
            a = [float(v) for v in imu.accelerometer]
            gn = math.sqrt(sum(v * v for v in g))
            an = math.sqrt(sum(v * v for v in a))
            temp = float(imu.temperature)

            warn = "  ← 기울기 주의" if (abs(r) > 15 or abs(p) > 15) else ""
            print(f"  {r:+8.2f} {p:+8.2f} {y:+8.2f} | "
                  f"{gn:7.3f} {an:8.3f} | {temp:4.0f}°C{warn}   ", end="\r",
                  flush=True)

            if f:
                f.write(f"{time.time() - t_start:.3f},{m.tick},"
                        f"{r:.3f},{p:.3f},{y:.3f},"
                        f"{g[0]:.4f},{g[1]:.4f},{g[2]:.4f},"
                        f"{a[0]:.4f},{a[1]:.4f},{a[2]:.4f},{temp:.1f}\n")
            time.sleep(period)
    except KeyboardInterrupt:
        print("\n\n  종료.")
    finally:
        if f:
            f.close()
            print(f"  기록 저장 완료 → {args.csv}")


if __name__ == "__main__":
    main()
