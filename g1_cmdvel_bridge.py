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

테스트(로봇을 실제로 걷게 한다 — 행어·공간·리모컨 확인 후):
    ros2 topic pub -r 10 /cmd_vel geometry_msgs/msg/Twist \\
        "{linear: {x: 0.2}, angular: {z: 0.0}}"
"""
import argparse
import signal
import sys
import time

# ── 안전 상한 (g1_walk_test.py 와 동일) ──────────────────────────────
LIMIT_VX = 0.3      # m/s   전후
LIMIT_VY = 0.2      # m/s   좌우
LIMIT_VYAW = 0.4    # rad/s 회전

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
