#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_real_monitor.py — G1 실기체 관절 상태 모니터링 스테이션 (읽기 전용).

교재4 대응 : 6.3(모니터링 담당 핵심 임무·콜 규약) / SOP ③('상태 정상' 콜의 근거)
             / 6.5 미션 ②(기준선 커닝페이퍼) / 3.2(low state 는 읽기 전용).
경로       : SDK 창구(rt/lowstate 직접 구독) — 교재 3.1 의 '두 창구' 중 하나.
             unitree_ros2 가 떠 있다면 ros2 topic echo 병행도 가능(같은 은행, 두 창구).
이 스크립트는 로봇에 어떤 명령도 보내지 않는다.

세 가지 모드:
  precheck  조작 전 점검 → PASS/CHECK 표 + 콜 제안                    (SOP ③)
  baseline  조용한 상태(행어·Damp 또는 기립 직후) 기준선 저장            (6.3)
  watch     기준선 대비 실시간 감시 — 이상 시 '콜 문구'를 그대로 출력    (6.3)

사용 예 (실기체 · 유선 인터페이스 enp2s0):
  python3 g1_real_monitor.py precheck --iface enp2s0
  python3 g1_real_monitor.py baseline --iface enp2s0 --sec 15
  python3 g1_real_monitor.py watch    --iface enp2s0 --focus 4 5 10 11
"""
import argparse
import json
import math
import os
import sys
import time
import datetime as _dt

# 29자유도 구성 기준 관절 인덱스 지도 — 우리 기체·저장소 문서로 검증할 것(교재 3.4 미션 ②).
G1_JOINTS = {
    0: "L_hip_pitch", 1: "L_hip_roll", 2: "L_hip_yaw", 3: "L_knee",
    4: "L_ankle_pitch", 5: "L_ankle_roll",
    6: "R_hip_pitch", 7: "R_hip_roll", 8: "R_hip_yaw", 9: "R_knee",
    10: "R_ankle_pitch", 11: "R_ankle_roll",
    12: "waist_yaw", 13: "waist_roll", 14: "waist_pitch",
    15: "L_shoulder_pitch", 16: "L_shoulder_roll", 17: "L_shoulder_yaw",
    18: "L_elbow", 19: "L_wrist_roll", 20: "L_wrist_pitch", 21: "L_wrist_yaw",
    22: "R_shoulder_pitch", 23: "R_shoulder_roll", 24: "R_shoulder_yaw",
    25: "R_elbow", 26: "R_wrist_roll", 27: "R_wrist_pitch", 28: "R_wrist_yaw",
}
DEFAULT_FOCUS = [4, 5, 10, 11, 3, 9]      # 발목 4개 + 무릎 2개 — 균형의 최전선(교재 2.1)
BASELINE_PATH = "g1_baseline.json"


def jname(i):
    return G1_JOINTS.get(i, f"joint{i}")


def motor_temp(m):
    """MotorState_.temperature 는 int16[2] 배열(2026-07 IDL) — 최댓값 사용, 구버전 방어."""
    t = getattr(m, "temperature", None)
    if t is None:
        return float("nan")
    try:
        return float(max(t))
    except TypeError:
        return float(t)


class StateBuffer:
    def __init__(self):
        self.msg = None
        self.stamp = 0.0
        self.count = 0

    def cb(self, msg):
        self.msg = msg
        self.stamp = time.time()
        self.count += 1


def connect(args):
    try:
        from unitree_sdk2py.core.channel import (ChannelFactoryInitialize,
                                                 ChannelSubscriber)
        from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowState_
    except ImportError as e:
        sys.exit("unitree_sdk2py 를 찾을 수 없습니다 — 운영가이드 0장 설치 절차 참조.\n"
                 f"(원인: {e})")
    if os.environ.get("CYCLONEDDS_URI"):
        ChannelFactoryInitialize(args.domain)     # 인터페이스는 URI 가 지정
    else:
        ChannelFactoryInitialize(args.domain, args.iface)
    buf = StateBuffer()
    sub = ChannelSubscriber("rt/lowstate", LowState_)
    sub.Init(buf.cb, 10)
    t0 = time.time()
    while buf.msg is None and time.time() - t0 < 4.0:
        time.sleep(0.05)
    if buf.msg is None:
        sys.exit("[실패] rt/lowstate 미수신 — 확인 순서: ① 로봇 전원 ② 유선 연결·"
                 "PC IP(192.168.123.x) ③ --iface 이름(ip addr) ④ --domain(실기체 0)")
    return buf


def measure_hz(buf, sec=2.0):
    c0, t0 = buf.count, time.time()
    time.sleep(sec)
    return (buf.count - c0) / max(time.time() - t0, 1e-6)


def rpy_deg(msg):
    r = msg.imu_state.rpy
    return (math.degrees(float(r[0])), math.degrees(float(r[1])),
            math.degrees(float(r[2])))


# ── precheck : SOP ③ '상태 정상' 콜의 근거 만들기 ─────────────────────
def cmd_precheck(buf, args):
    print("\n[precheck] 조작 전 상태 점검 — 교재 3.2 '조작 전 확인 루틴'의 코드판")
    hz = measure_hz(buf)
    msg = buf.msg
    n = args.joints
    taus = [abs(float(msg.motor_state[i].tau_est)) for i in range(n)]
    temps = [motor_temp(msg.motor_state[i]) for i in range(n)]
    roll, pitch, yaw = rpy_deg(msg)
    imax_tau = max(range(n), key=lambda i: taus[i])
    imax_tmp = max(range(n), key=lambda i: (temps[i] if temps[i] == temps[i] else -1))
    nan_found = any(v != v for v in taus + temps + [roll, pitch])

    checks = [
        ("상태 스트림", hz > 100,
         f"{hz:.0f} Hz (휴머노이드는 빠른 갱신이 정상 — 교재 3.2)"),
        ("tick 진행", True, f"tick={msg.tick}, mode_machine={msg.mode_machine}, "
                            f"mode_pr={msg.mode_pr}"),
        ("IMU 기울기", abs(roll) < 15 and abs(pitch) < 15,
         f"roll {roll:+.1f}° / pitch {pitch:+.1f}° (행어 거치 자세 기준)"),
        ("모터 온도", temps[imax_tmp] < args.temp_warn,
         f"최고 {temps[imax_tmp]:.0f}°C @ {jname(imax_tmp)} "
         f"(주의 {args.temp_warn}°C / 중단 {args.temp_max}°C)"),
        ("토크 수준", True,
         f"최대 |tau| {taus[imax_tau]:.1f} Nm @ {jname(imax_tau)} "
         + ("→ Damp 추정(≈0)" if taus[imax_tau] < 3.0 else "→ 관절에 힘 실림(기립 계열)")),
        ("NaN 없음", not nan_found, "데이터 무결성"),
    ]
    ok = True
    for name, passed, detail in checks:
        mark = "PASS " if passed else "CHECK"
        ok = ok and passed
        print(f"  [{mark}] {name:<8s} {detail}")
    if temps[imax_tmp] >= args.temp_max:
        ok = False
        print(f"  [중단] 온도 {temps[imax_tmp]:.0f}°C ≥ {args.temp_max}°C — 정리 모드(교재 3.2)")
    print()
    if ok:
        print('  → 콜: "상태 정상"  (SOP ③)')
    else:
        print('  → 콜: "점검 필요 — CHECK 항목 보고"  (에러 위에 명령을 쌓지 않는다)')


# ── baseline : 기준선 캡처 (6.3 "무엇이 정상인가") ─────────────────────
def cmd_baseline(buf, args):
    n = args.joints
    print(f"\n[baseline] {args.sec:.0f}초간 기준선 캡처 — 로봇은 조용한 상태"
          "(행어·Damp 또는 기립 직후)여야 의미가 있습니다.")
    tau_max = [0.0] * n
    tau_sum = [0.0] * n
    tmp_max = [0.0] * n
    rolls, pitches = [], []
    k = 0
    t_end = time.time() + args.sec
    while time.time() < t_end:
        msg = buf.msg
        for i in range(n):
            a = abs(float(msg.motor_state[i].tau_est))
            tau_max[i] = max(tau_max[i], a)
            tau_sum[i] += a
            tmp_max[i] = max(tmp_max[i], motor_temp(msg.motor_state[i]))
        r = msg.imu_state.rpy
        rolls.append(float(r[0]))
        pitches.append(float(r[1]))
        k += 1
        time.sleep(0.02)
    base = {
        "meta": {"time": _dt.datetime.now().isoformat(timespec="seconds"),
                 "sec": args.sec, "samples": k, "joints": n, "iface": args.iface},
        "joints": {str(i): {"name": jname(i),
                            "tau_mean": round(tau_sum[i] / max(k, 1), 3),
                            "tau_max": round(tau_max[i], 3),
                            "temp_max": round(tmp_max[i], 1)} for i in range(n)},
        "imu": {"roll_mean": round(sum(rolls) / len(rolls), 4),
                "pitch_mean": round(sum(pitches) / len(pitches), 4)},
    }
    with open(args.baseline, "w", encoding="utf-8") as f:
        json.dump(base, f, ensure_ascii=False, indent=1)
    print(f"  저장 → {args.baseline} ({k} 샘플)")
    top = sorted(range(n), key=lambda i: tau_max[i], reverse=True)[:5]
    print("\n  기준선 커닝페이퍼(교재 6.5 미션 ②) — |tau| 상위 관절:")
    for i in top:
        print(f"    {jname(i):<16s} 평소 |tau| ≤ {tau_max[i]:.1f} Nm, "
              f"온도 ≤ {tmp_max[i]:.0f}°C")
    print(f"    IMU 평소 roll {math.degrees(base['imu']['roll_mean']):+.1f}° / "
          f"pitch {math.degrees(base['imu']['pitch_mean']):+.1f}°")


# ── watch : 실시간 감시 + 콜 규약 (6.3) ───────────────────────────────
def cmd_watch(buf, args):
    n = args.joints
    if not os.path.exists(args.baseline):
        sys.exit(f"기준선 파일이 없습니다 → 먼저 baseline 을 실행하세요 ({args.baseline})")
    with open(args.baseline, encoding="utf-8") as f:
        base = json.load(f)
    thr = {}
    for i in range(n):
        b = base["joints"].get(str(i), {"tau_max": 0.0})
        thr[i] = max(b["tau_max"] * args.tau_ratio, args.tau_min)
    roll0 = base["imu"]["roll_mean"]
    pitch0 = base["imu"]["pitch_mean"]

    focus = args.focus or DEFAULT_FOCUS
    csv_path = f"monitor_log_{_dt.datetime.now():%m%d_%H%M%S}.csv"
    fcsv = open(csv_path, "w", encoding="utf-8")
    fcsv.write("t,tick,roll_deg,pitch_deg," +
               ",".join(f"{jname(i)}_q,{jname(i)}_tau" for i in focus) + "\n")

    print(f"\n[watch] 감시 시작 — 기준선 {base['meta']['time']} / "
          f"토크 경보 max(기준×{args.tau_ratio}, {args.tau_min}Nm) / "
          f"기울기 경보 기준 대비 {math.degrees(args.tilt):.1f}° / 로그 {csv_path}")
    print("  콜 규약(교재 6.3): 짧고, 크게, 즉시 — 판단은 멘토에게. Ctrl+C 로 종료.\n")

    cooldown = {}
    tilt_hist = []              # (t, tilt편차크기) — '서서히 증가' 감지용
    alerts = 0
    t0 = time.time()
    last_line = 0.0
    try:
        while True:
            now = time.time()
            if now - buf.stamp > 0.5:
                if cooldown.get("stall", 0) < now:
                    print('\a  >>> [콜] "모니터링 끊김" — 데이터 없이 진행하지 않는다')
                    cooldown["stall"] = now + 2.0
                    alerts += 1
                time.sleep(0.1)
                continue
            msg = buf.msg
            r = msg.imu_state.rpy
            droll = float(r[0]) - roll0
            dpitch = float(r[1]) - pitch0
            tilt = math.hypot(droll, dpitch)
            tilt_hist.append((now, tilt))
            tilt_hist = [(t, v) for t, v in tilt_hist if now - t < 5.0]

            # ① 토크 이상
            for i in range(n):
                a = abs(float(msg.motor_state[i].tau_est))
                if a > thr[i] and cooldown.get(("tau", i), 0) < now:
                    print(f'\a  >>> [콜] "토크 이상 — {jname(i)}"  '
                          f'|tau|={a:.1f}Nm (기준 {thr[i]:.1f})')
                    cooldown[("tau", i)] = now + 2.0
                    alerts += 1
            # ② 기울기 — 즉시 초과 또는 서서히 증가
            grow = (len(tilt_hist) > 20 and
                    tilt_hist[-1][1] - tilt_hist[0][1] > args.tilt * 0.5)
            if (tilt > args.tilt or grow) and cooldown.get("tilt", 0) < now:
                print(f'\a  >>> [콜] "기울기 증가 중"  편차 {math.degrees(tilt):.1f}° '
                      f'(roll {math.degrees(droll):+.1f}° / pitch {math.degrees(dpitch):+.1f}°)')
                cooldown["tilt"] = now + 2.0
                alerts += 1
            # ③ 온도
            for i in range(n):
                tp = motor_temp(msg.motor_state[i])
                if tp >= args.temp_warn and cooldown.get(("tmp", i), 0) < now:
                    print(f'\a  >>> [콜] "온도 주의 — {jname(i)}"  {tp:.0f}°C')
                    cooldown[("tmp", i)] = now + 10.0
                    alerts += 1

            # 1초마다 관측 라인 + CSV 10Hz
            if now - last_line > 1.0:
                fx = " | ".join(f"{jname(i)} q={float(msg.motor_state[i].q):+.3f}"
                                f" tau={float(msg.motor_state[i].tau_est):+5.1f}"
                                for i in focus[:3])
                print(f"  t={now - t0:6.1f}s  tilt {math.degrees(tilt):4.1f}°  {fx}")
                last_line = now
            fcsv.write(f"{now - t0:.2f},{msg.tick},"
                       f"{math.degrees(float(r[0])):.2f},{math.degrees(float(r[1])):.2f},"
                       + ",".join(f"{float(msg.motor_state[i].q):.4f},"
                                  f"{float(msg.motor_state[i].tau_est):.2f}"
                                  for i in focus) + "\n")
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        fcsv.close()
        print(f"\n[watch 종료] 경보 {alerts}회 · 로그 {csv_path}"
              " — 주말 분석 자료(교재 6.4 '데이터는 남긴다')")


def main():
    ap = argparse.ArgumentParser(description="G1 실기체 모니터링 (읽기 전용)")
    ap.add_argument("cmd", choices=["precheck", "baseline", "watch"])
    ap.add_argument("--iface", help="예: enp2s0 (CYCLONEDDS_URI 설정 시 생략 가능)")
    ap.add_argument("--domain", type=int, default=0, help="DDS domain (실기체 0)")
    ap.add_argument("--joints", type=int, default=29, help="감시 관절 수(구성에 따라 조정)")
    ap.add_argument("--sec", type=float, default=15.0, help="baseline 캡처 시간")
    ap.add_argument("--baseline", default=BASELINE_PATH)
    ap.add_argument("--focus", type=int, nargs="*", help="집중 관찰 관절 인덱스")
    ap.add_argument("--tau-ratio", type=float, default=2.5)
    ap.add_argument("--tau-min", type=float, default=8.0)
    ap.add_argument("--tilt", type=float, default=0.12, help="기울기 경보 편차[rad]")
    ap.add_argument("--temp-warn", type=float, default=60.0)
    ap.add_argument("--temp-max", type=float, default=75.0)
    args = ap.parse_args()

    buf = connect(args)
    {"precheck": cmd_precheck, "baseline": cmd_baseline, "watch": cmd_watch}[args.cmd](buf, args)


if __name__ == "__main__":
    main()
