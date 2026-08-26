#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_joint_tap.py — [tapenv 전용] /lowstate 관절각 29개 → UDP 전달

odom tap 과 같은 패턴의 '관절판'. 로봇 lowstate(고주파)에서 관절각만
뽑아 30Hz 로 낮춰 UDP:17778 로 보낸다. 반대편 g1_joint_relay.py 가
/joint_states 로 발행하면 RViz 의 G1 모형 다리가 실제로 걷는다.

사용 (tapenv 터미널 — odom tap 과 별개 터미널):
    source ~/g1_real/tapenv.sh
    python3 ~/g1_real/g1_joint_tap.py
"""
import json
import socket
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from unitree_hg.msg import LowState

UDP_ADDR = ("127.0.0.1", 17778)
SEND_HZ = 30.0


class JointTap(Node):
    def __init__(self):
        super().__init__("g1_joint_tap")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.n = 0
        self.last_send = 0.0
        qos = QoSProfile(depth=10,
                         reliability=ReliabilityPolicy.BEST_EFFORT,
                         history=HistoryPolicy.KEEP_LAST)
        self.sub = self.create_subscription(LowState, "/lowstate", self.cb, qos)
        self.get_logger().info("/lowstate 구독 → 관절각 29개 → UDP:17778 (30Hz)")
        self.create_timer(5.0, self.health)

    def cb(self, m: LowState):
        now = time.monotonic()
        if now - self.last_send < 1.0 / SEND_HZ:
            return
        self.last_send = now
        # G1 29dof: motor_state[0..28].q — URDF revolute 순서와 1:1 동일 검증됨
        # (발목은 PR 모드 기준 pitch/roll — 시각화 용도로 충분)
        q = [float(m.motor_state[i].q) for i in range(29)]
        self.sock.sendto(json.dumps(q).encode(), UDP_ADDR)
        self.n += 1
        if self.n % 150 == 1:
            self.get_logger().info(
                f"#{self.n}  무릎L={q[3]:+.2f} 팔꿈치L={q[18]:+.2f} rad")

    def health(self):
        if self.n == 0:
            self.get_logger().warn("수신 0건 — 로봇 전원? tapenv 진입 확인")


def main():
    rclpy.init()
    node = JointTap()
    # LowState 스트림엔 간헐적으로 파이썬 변환 불가 패킷(독약 메시지)이 섞인다.
    # 그 한 개 때문에 프로세스가 죽지 않도록, 메시지 단위로 삼키고 계속 돈다.
    bad = 0
    try:
        while rclpy.ok():
            try:
                rclpy.spin_once(node, timeout_sec=0.2)
            except RuntimeError as e:
                bad += 1
                if bad % 50 == 1:
                    node.get_logger().warn(f"변환 불가 메시지 건너뜀 (누적 {bad}) — {e}")
    except KeyboardInterrupt:
        pass
    node.destroy_node()


if __name__ == "__main__":
    main()
