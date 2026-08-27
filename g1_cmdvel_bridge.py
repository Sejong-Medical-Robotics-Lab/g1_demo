#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_cmdvel_bridge.py — ROS 2 `/cmd_vel` → Unitree SDK `SetVelocity()` 브리지.

    Nav2 (또는 teleop) → /cmd_vel (geometry_msgs/Twist)
        → 이 노드 → loco.SetVelocity(vx, vy, vyaw, 0.5) → G1

Nav2 는 `/cmd_vel` 로 속도를 내보낼 뿐 로봇을 직접 움직이지 못한다.
그 명령을 받아 Unitree SDK 로 옮기는 것이 이 노드의 전부다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
왜 한 프로세스에 rclpy 와 SDK 를 같이 넣을 수 있나
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ROS 2 Jazzy 의 cyclonedds(0.10.4)와 SDK 가 요구하는 0.10.2 가 충돌해
`buffer overflow detected` 로 죽는 문제가 있었다. 다음 두 가지로 피한다.

  1. RMW 를 FastDDS 로 — ROS 2 쪽이 cyclonedds 를 로드하지 않게 한다
         export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
  2. CYCLONEDDS_URI 로 인터페이스 지정 — SDK 에 인터페이스 이름을 인자로
     넘기면 죽는다(g1_env.sh 가 자동 설정)

실행 전 반드시:
    g1                                      # venv + CYCLONEDDS_URI
    source /opt/ros/jazzy/setup.bash
    export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

안전 설계 — g1_walk_test.py 와 동일한 데드맨 방식:

  · `SetVelocity` 의 duration 을 짧게(0.5s) 주고 그보다 빠른 주기(0.2s)로
    재전송한다. 이 노드가 죽거나 통신이 끊기면 로봇이 스스로 멈춘다.
  · `/cmd_vel` 이 CMD_TIMEOUT(0.5s) 동안 안 오면 정지 명령으로 전환한다.
    Nav2 가 죽든, 목표에 도달해 발행을 멈추든 로봇은 선다.
  · 속도는 안전 상한으로 clamp 한다. Nav2 설정이 잘못돼도 튀지 않는다.
  · SIGINT(Ctrl+C) 시 정지 명령을 반복 전송한다. Damp 는 보내지 않는다 —
    걷는 중에 힘이 빠지면 더 위험하다.

사용:
    python3 g1_cmdvel_bridge.py --iface $G1_IFACE
    python3 g1_cmdvel_bridge.py --iface $G1_IFACE --dry-run   # 로봇 없이 수신만 확인

※ 하한선 기본 폐지 (2026-08-27): 속도 상향(0.5) 체제에서 하한 불필요 실증
   — 저속(0.15 이하) 운용으로 돌아갈 때만 인자로 부활시킬 것:
     --min-vx 0.10 --min-vyaw 0.10 --min-vyaw-inplace 0.25
   (구 실측 기록 보존용 원문: 실행 하한선 실기체 실측 기반):
   - 전진 중 회전: 0.10 미만 → 0.10 으로 (호 회전은 0.10 부터 정상)
   - 제자리 회전: 0.25 미만 → 0.25 로 ★중요: G1 은 작은 제자리 회전
     명령(≤0.15)을 받으면 돌지 않고 옆걸음으로 벽까지 미끄러진다.
     0.25 부터 정상 회전을 실기체로 확인했다.
   - 전진: 0.05 미만 → 0.05
   끄려면 각각 0 을 넘긴다 (--min-vyaw 0 등).

테스트(로봇을 실제로 걷게 한다 — 행어·공간·리모컨 확인 후):
    ros2 topic pub -r 10 /cmd_vel geometry_msgs/msg/Twist \\
        "{linear: {x: 0.2}, angular: {z: 0.0}}"
"""
import argparse
import signal
import sys
import time

# ── 안전 상한 (g1_walk_test.py 와 동일) ──────────────────────────────
LIMIT_VX = 1.0    # 날것 기본 (2026-08-27 검증) — 실질 상한은 Nav2 yaml 0.5
LIMIT_VY = 0.5    # 날것 기본 (2026-08-27)
LIMIT_VYAW = 2.0  # 날것 기본 (2026-08-27) — 실질 상한은 Nav2 yaml 0.6

SEND_PERIOD = 0.2    # SetVelocity 재전송 주기 [s]
CMD_DURATION = 0.5   # 명령 유효 시간 [s] — 데드맨. SEND_PERIOD 보다 커야 한다
CMD_TIMEOUT = 0.5    # /cmd_vel 이 이 시간 이상 안 오면 정지로 간주 [s]

FSM_REGULAR = 501    # 보행·팔 액션이 모두 되는 상태


def clamp(v, lim):
    return max(-lim, min(lim, v))


def main():
    ap = argparse.ArgumentParser(description="/cmd_vel → G1 SetVelocity 브리지")
    ap.add_argument("--iface", help="예: enx... (CYCLONEDDS_URI 설정 시 생략 가능)")
    ap.add_argument("--domain", type=int, default=0, help="DDS domain (실기체 0)")
    ap.add_argument("--topic", default="/cmd_vel")
    ap.add_argument("--dry-run", action="store_true",
                    help="로봇에 명령을 보내지 않고 수신만 출력")
    ap.add_argument("--max-vx", type=float, default=LIMIT_VX)
    ap.add_argument("--max-vy", type=float, default=LIMIT_VY)
    ap.add_argument("--max-vyaw", type=float, default=LIMIT_VYAW)
    # ── 트림(보정 편향) ──────────────────────────────────────────────
    # 로봇이 직진 명령에도 일정하게 한쪽으로 새는 경우(보행 비대칭,
    # 라이다 장착 yaw 오차 등)를 상수로 상쇄한다. 비행기의 트림 탭과
    # 같은 개념. 전진 중일 때만 더해지고, 정지·데드맨 상태에는 절대
    # 더해지지 않는다(안전).
    #
    # 값 찾는 법: Nav2 끄고 순수 직진을 보내 어느 쪽으로 새는지 관찰 —
    #   ros2 topic pub -r 10 /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.12}}"
    # 오른쪽으로 새면 --trim-vyaw 를 +0.02 부터 조금씩 올려가며(+ = 좌회전)
    # 직진이 되는 값을 찾는다. 좌우 걸음(vy)으로 잡고 싶으면 --trim-vy
    # (+ = 왼쪽 사이드스텝).
    ap.add_argument("--trim-vyaw", type=float, default=0.0,
                    help="전진 중 항상 더할 회전 편향 [rad/s], + = 좌회전")
    ap.add_argument("--trim-vy", type=float, default=0.0,
                    help="전진 중 항상 더할 횡이동 편향 [m/s], + = 왼쪽")
    # ── 실행 하한선(데드밴드 보상) ──────────────────────────────────
    # G1 보행 컨트롤러는 아주 작은 속도 명령을 무시한다(데드밴드).
    # 실주행에서 확인된 증상: Nav2 가 vyaw=0.04 처럼 작은 회전을 계속
    # 보내는데 로봇은 미동도 없음 → 진행 감시기가 "Failed to make
    # progress" 로 중단. 0이 아닌 명령이 이 하한보다 작으면 부호를
    # 유지한 채 하한값으로 올려서, 보내는 명령 = 실행되는 명령이 되게
    # 한다. 0 명령(정지)은 절대 건드리지 않는다.
    # 하한값 찾기: ros2 topic pub 으로 회전만 0.05→0.08→0.10 올려가며
    # 로봇이 실제로 돌기 시작하는 값을 확인해서 넣는다.
    ap.add_argument("--min-vyaw", type=float, default=0.0,
                    help="전진 중(|vx|>0.02) 0이 아닌 회전 명령의 실행 하한 "
                         "[rad/s] (0=끔). 걸으면서 도는 호는 0.10 부터 잘 "
                         "동작함을 실주행으로 확인 (2026-08-25)")
    ap.add_argument("--min-vyaw-inplace", type=float, default=0.0,
                    help="제자리 회전(|vx|<0.02) 시 회전 명령의 실행 하한 "
                         "[rad/s]. ★ G1 은 이보다 작은 제자리 회전 명령을 "
                         "받으면 돌지 않고 옆걸음으로 미끄러져 위험하다 — "
                         "0.15 에서 게걸음으로 벽에 간 것을 실기체로 확인, "
                         "0.25 부터 정상 회전 확인 (2026-08-25)")
    ap.add_argument("--min-vx", type=float, default=0.0,
                    help="0이 아닌 전진 명령의 실행 하한 [m/s] (0=기능 끔). "
                         "기본 0.05")
    args = ap.parse_args()

    import os
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
    from geometry_msgs.msg import Twist

    loco = None
    if not args.dry_run:
        from unitree_sdk2py.core.channel import ChannelFactoryInitialize
        from unitree_sdk2py.g1.loco.g1_loco_client import LocoClient
        if os.environ.get("CYCLONEDDS_URI"):
            ChannelFactoryInitialize(args.domain)     # 인터페이스는 URI 가 지정
        else:
            if not args.iface:
                sys.exit("--iface 가 필요합니다 (또는 g1 으로 CYCLONEDDS_URI 설정).")
            ChannelFactoryInitialize(args.domain, args.iface)
        loco = LocoClient()
        loco.SetTimeout(5.0)
        loco.Init()

        try:
            code, fsm = loco.GetFsmId()
            print(f"  현재 FSM: {fsm if code == 0 else '조회 실패'}")
            if code == 0 and fsm != FSM_REGULAR:
                print(f"  [경고] 레귤러 모드(FSM {FSM_REGULAR})가 아닙니다 — "
                      "보행 명령이 거부될 수 있습니다.")
                print("         먼저 g1_stand_test.py 로 501 까지 올리세요.")
        except Exception as e:
            print(f"  FSM 조회 실패({e}) — 계속 진행합니다.")

    class CmdVelBridge(Node):
        def __init__(self):
            super().__init__("g1_cmdvel_bridge")
            self.vx = self.vy = self.vyaw = 0.0
            self.last_cmd = 0.0          # 마지막 /cmd_vel 수신 시각
            self.stopped = True          # 현재 정지 상태인지(로그 억제용)
            self.n_sent = 0

            # Nav2 는 기본적으로 best-effort 로 /cmd_vel 을 낸다.
            qos = QoSProfile(depth=10,
                             reliability=ReliabilityPolicy.BEST_EFFORT,
                             history=HistoryPolicy.KEEP_LAST)
            self.create_subscription(Twist, args.topic, self.on_cmd, qos)
            self.create_timer(SEND_PERIOD, self.tick)

            self.get_logger().info(
                f"구독 {args.topic} → SetVelocity "
                f"(재전송 {SEND_PERIOD}s / 유효 {CMD_DURATION}s / "
                f"타임아웃 {CMD_TIMEOUT}s)")
            self.get_logger().info(
                f"안전 상한 |vx|≤{args.max_vx} |vy|≤{args.max_vy} "
                f"|vyaw|≤{args.max_vyaw}"
                + (f"   트림 vyaw{args.trim_vyaw:+.3f} vy{args.trim_vy:+.3f}"
                   if (args.trim_vyaw or args.trim_vy) else "")
                + ("   [DRY-RUN — 로봇에 보내지 않음]" if args.dry_run else ""))

        def on_cmd(self, msg):
            self.vx = clamp(float(msg.linear.x), args.max_vx)
            self.vy = clamp(float(msg.linear.y), args.max_vy)
            self.vyaw = clamp(float(msg.angular.z), args.max_vyaw)
            self.last_cmd = time.monotonic()

        def tick(self):
            # /cmd_vel 이 끊기면 정지 — Nav2 가 죽어도 로봇은 선다
            fresh = (time.monotonic() - self.last_cmd) < CMD_TIMEOUT
            vx, vy, vyaw = (self.vx, self.vy, self.vyaw) if fresh else (0.0, 0.0, 0.0)

            # 트림: 실제로 전진 중일 때만 편향을 더한다.
            # 정지·데드맨(위에서 0 처리됨)·제자리 회전에는 안 더한다 —
            # 새는 건 걷는 동안이고, 서 있는 로봇을 트림이 움직이면 안 된다.
            if fresh and abs(vx) > 0.02:
                vy = clamp(vy + args.trim_vy, args.max_vy)
                vyaw = clamp(vyaw + args.trim_vyaw, args.max_vyaw)

            # 실행 하한선: 0이 아닌 작은 명령을 로봇이 실제로 실행하는
            # 최소값까지 끌어올린다 (부호 유지, 0은 그대로 0).
            # ★ 회전 하한은 상황에 따라 다르다 (2026-08-25 실기체 확인):
            #   - 전진 중 호 회전: 0.10 부터 정상
            #   - 제자리 회전:     0.25 미만이면 돌지 않고 옆걸음으로
            #     미끄러진다(게걸음 → 벽 충돌 위험). 그래서 더 높은
            #     하한을 적용해 그 위험 구간의 명령이 아예 안 나가게 한다.
            moving = abs(vx) >= 0.02
            yaw_floor = args.min_vyaw if moving else args.min_vyaw_inplace
            if yaw_floor > 0 and 1e-6 < abs(vyaw) < yaw_floor:
                vyaw = yaw_floor if vyaw > 0 else -yaw_floor
            if args.min_vx > 0 and 1e-6 < abs(vx) < args.min_vx:
                vx = args.min_vx if vx > 0 else -args.min_vx

            moving = any(abs(v) > 1e-6 for v in (vx, vy, vyaw))
            if moving:
                self.stopped = False
                print(f"    vx={vx:+.2f} vy={vy:+.2f} vyaw={vyaw:+.2f}"
                      f"{'' if fresh else '  (타임아웃 → 정지)'}   ",
                      end="\r", flush=True)
            elif not self.stopped:
                self.stopped = True
                print(" " * 70, end="\r")
                self.get_logger().info(
                    "정지" + ("" if fresh else " (cmd_vel 끊김)"))

            if args.dry_run:
                return
            try:
                loco.SetVelocity(vx, vy, vyaw, CMD_DURATION)
                self.n_sent += 1
            except Exception as e:
                self.get_logger().warn(f"SetVelocity 실패: {e}")

        def stop_hard(self):
            """종료 시 — 정지만 보낸다. Damp 는 보내지 않는다."""
            if args.dry_run or loco is None:
                return
            for _ in range(5):
                try:
                    loco.SetVelocity(0.0, 0.0, 0.0, 0.5)
                except Exception:
                    pass
                time.sleep(0.05)

    rclpy.init()
    node = CmdVelBridge()

    def on_sigint(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, on_sigint)

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        print("\n  중단 — 정지 명령 전송")
    finally:
        node.stop_hard()
        node.destroy_node()
        try:
            rclpy.shutdown()
        except Exception:
            pass
        print("  종료. 로봇이 완전히 정지했는지 눈으로 확인하세요.")


if __name__ == "__main__":
    main()
