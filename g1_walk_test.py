#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_walk_test.py — 2단계: 보행 단독 검증 (데드맨 방식).

이 프로젝트에서 가장 위험한 단계다. 설계 원칙 3가지:

  ① Move() 를 쓰지 않는다.
     Move(vx,vy,vyaw) 는 SetVelocity(..., duration=1) 이고,
     continous_move=True 는 duration=864000초(10일)라 스크립트가 죽으면
     로봇이 계속 걷는다. 여기서는 SetVelocity 를 직접 호출한다.

  ② 데드맨(dead-man).
     duration 을 짧게(기본 0.5초) 주고, 그보다 빠른 주기(기본 0.2초)로
     재전송한다. 프로세스가 죽거나 통신이 끊기면 0.5초 안에 스스로 멈춘다.

  ③ 어떤 경로로 빠져나가도 StopMove → (선택) Damp.

사용:
  python3 g1_walk_test.py --dry-run
  python3 g1_walk_test.py --iface enp2s0 --vx 0.2 --sec 3          # 짧은 전진
  python3 g1_walk_test.py --iface enp2s0 --vyaw 0.3 --sec 3        # 제자리 회전
  python3 g1_walk_test.py --iface enp2s0 --preset forward_stop_turn
  python3 g1_walk_test.py --iface enp2s0 --preset forward --audio

전제: 균형 제어(FSM 500)에 이미 올라와 있어야 한다.
      먼저 g1_stand_test.py 로 기립까지 검증하고 'k=기립 유지'로 종료한 뒤 실행.
"""
import argparse
import sys
import time

from g1_common import (FSM, AbortRun, G1Link, RealCommandError, banner,
                       call_text, gate, safe_damp)

# 안전 상한 — 이 값을 넘는 인자는 자동으로 잘린다(clamp).
LIMIT_VX = 0.3      # m/s  전후
LIMIT_VY = 0.2      # m/s  좌우
LIMIT_VYAW = 0.4    # rad/s 회전
LIMIT_SEC = 10.0    # 한 구간 최대 지속 시간

SEND_PERIOD = 0.2   # 재전송 주기 [s]
CMD_DURATION = 0.5  # 명령 유효 시간 [s]  ← 데드맨. 반드시 SEND_PERIOD 보다 크게.

# 프리셋 — (라벨, vx, vy, vyaw, 지속초)
PRESETS = {
    "forward": [
        ("짧은 전진", 0.2, 0.0, 0.0, 3.0),
    ],
    "forward_stop_turn": [
        ("전진", 0.2, 0.0, 0.0, 3.0),
        ("정지", 0.0, 0.0, 0.0, 2.0),
        ("좌회전", 0.0, 0.0, 0.3, 3.0),
        ("정지", 0.0, 0.0, 0.0, 2.0),
    ],
    "lateral": [
        ("좌측 이동", 0.0, 0.15, 0.0, 3.0),
        ("정지", 0.0, 0.0, 0.0, 2.0),
    ],
}


def clamp(v, lim, name):
    if abs(v) > lim:
        print(f"  [제한] {name} {v:+.2f} → {lim if v > 0 else -lim:+.2f} (안전 상한)")
        return lim if v > 0 else -lim
    return v


def drive(link, label, vx, vy, vyaw, sec):
    """한 구간을 데드맨 방식으로 실행."""
    vx = clamp(vx, LIMIT_VX, "vx")
    vy = clamp(vy, LIMIT_VY, "vy")
    vyaw = clamp(vyaw, LIMIT_VYAW, "vyaw")
    sec = min(sec, LIMIT_SEC)

    print(f"\n  ▶ {label}: vx={vx:+.2f} vy={vy:+.2f} vyaw={vyaw:+.2f}  {sec:.1f}s")
    moving = any(abs(v) > 1e-6 for v in (vx, vy, vyaw))
    link.announce(f"{label}합니다." if moving else "정지합니다.",
                  "walk" if moving else "balance")
    t_end = time.monotonic() + sec
    n = 0
    while time.monotonic() < t_end:
        link.set_velocity(vx, vy, vyaw, CMD_DURATION)
        n += 1
        remain = t_end - time.monotonic()
        print(f"      … 남은 {max(remain, 0):4.1f}s  (전송 {n}회)   ",
              end="\r", flush=True)
        time.sleep(min(SEND_PERIOD, max(remain, 0.01)))
    print()
    link.stop_move()
    print(f"      정지 전송 — {CMD_DURATION:.1f}s 내 완전 정지")


def main():
    ap = argparse.ArgumentParser(description="2단계 — 보행 단독 검증(데드맨)")
    ap.add_argument("--iface")
    ap.add_argument("--domain", type=int, default=0)
    ap.add_argument("--preset", choices=sorted(PRESETS),
                    help="미리 정의된 보행 시나리오")
    ap.add_argument("--vx", type=float, default=0.0, help="전후 [m/s]")
    ap.add_argument("--vy", type=float, default=0.0, help="좌우 [m/s]")
    ap.add_argument("--vyaw", type=float, default=0.0, help="회전 [rad/s]")
    ap.add_argument("--sec", type=float, default=3.0, help="지속 시간 [s]")
    ap.add_argument("--audio", action="store_true", help="음성 안내 + LED 색 표시")
    ap.add_argument("--volume", type=int, default=70, help="--audio 볼륨 0~100")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    plan = PRESETS[args.preset] if args.preset else \
        [("수동 지정", args.vx, args.vy, args.vyaw, args.sec)]

    banner("2단계 — 보행 단독 검증 (행어 · 멘토 확인 하)")
    print(f"\n  데드맨: {SEND_PERIOD:.1f}s 주기 재전송 / 명령 유효 {CMD_DURATION:.1f}s")
    print(f"  안전 상한: |vx|≤{LIMIT_VX} |vy|≤{LIMIT_VY} |vyaw|≤{LIMIT_VYAW} "
          f"구간≤{LIMIT_SEC:.0f}s")
    print("\n  실행 계획")
    for i, (label, vx, vy, vyaw, sec) in enumerate(plan, 1):
        print(f"   {i}. {label:<12s} vx={vx:+.2f} vy={vy:+.2f} vyaw={vyaw:+.2f} "
              f"{sec:.1f}s")

    if args.dry_run:
        print("\n  --dry-run: 여기까지가 실행 전 코드 리뷰용 출력입니다.")
        return
    if not args.iface:
        sys.exit("--iface 가 필요합니다. 리뷰만 하려면 --dry-run.")

    link = G1Link(args.iface, args.domain, with_arm=True,
                  with_audio=args.audio,
                  volume=args.volume if args.audio else None)

    print(f"\n  현재 FSM: {link.fsm_text()}")
    f = link.fsm()
    if f is not None and f != FSM.START:
        print(f"  [경고] 균형 제어(FSM {FSM.START})가 아닙니다 — 보행 명령이 거부될 수 있습니다.")

    gate("보행 공간이 확보되어 있고, 진행 방향에 사람·장애물이 없습니까?")
    gate("행어/안전 확보 상태이고 멘토가 비상 Damp 를 즉시 누를 수 있습니까?")
    gate("모니터링 담당이 watch 가동 중이고, 로봇이 균형 제어 상태입니까?")

    try:
        link.release_arm()   # 팔 제어가 잡혀 있으면 보행 전에 반납
        for label, vx, vy, vyaw, sec in plan:
            drive(link, label, vx, vy, vyaw, sec)
        link.announce("보행 시험을 마쳤습니다.", "balance")
        call_text("보행 시퀀스 완료")

    except KeyboardInterrupt:
        print()
        link.stop_move()
        safe_damp(link, "Ctrl+C 중단")
    except AbortRun as e:
        link.stop_move()
        safe_damp(link, str(e))
    except RealCommandError as e:
        link.stop_move()
        safe_damp(link, str(e))
    except Exception as e:
        link.stop_move()
        safe_damp(link, f"예외 {type(e).__name__}: {e}")
    finally:
        try:
            link.stop_move()    # 어떤 경로로 끝나든 마지막에 한 번 더
        except Exception:
            pass
        print("\n  종료 — 로봇이 완전히 정지했는지 육안으로 확인하세요.")


if __name__ == "__main__":
    main()
