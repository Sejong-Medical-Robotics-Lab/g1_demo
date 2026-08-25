#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_odom_tap_ros.py — [tapenv 전용] 로봇 내장 오도메트리 → UDP 전달

로봇이 표준 nav_msgs/Odometry 로 내장 오도메트리를 직접 발행함이
확인됐다 (/state_estimator/odom_pelvis — 골반 기준, base_link 와
개념 일치). 이걸 받아 UDP 로 relay(평소 터미널)에 넘긴다.

사용 (새 터미널, venv 없이):
    source ~/g1_real/tapenv.sh
    python3 ~/g1_real/g1_odom_tap_ros.py
    # 다른 토픽을 쓰려면: --topic /state_estimator/fusion_odom
"""
import argparse
import json
import math
import socket
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from nav_msgs.msg import Odometry

UDP_ADDR = ("127.0.0.1", 17777)


class TapRos(Node):
    def __init__(self, topic: str):
        super().__init__("g1_odom_tap_ros")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.n = 0
        self.last_log = 0.0
        qos = QoSProfile(depth=10,
                         reliability=ReliabilityPolicy.BEST_EFFORT,
                         history=HistoryPolicy.KEEP_LAST)
        self.sub = self.create_subscription(Odometry, topic, self.cb, qos)
        self.get_logger().info(f"{topic} 구독 → UDP:17777 (relay 로)")
        self.create_timer(5.0, self.health)

    def cb(self, m: Odometry):
        p = m.pose.pose.position
        o = m.pose.pose.orientation           # x,y,z,w
        yaw = math.atan2(2.0 * (o.w * o.z + o.x * o.y),
                         1.0 - 2.0 * (o.y * o.y + o.z * o.z))
        t = m.twist.twist
        pkt = json.dumps({
            "x": float(p.x), "y": float(p.y), "yaw": yaw,
            "vx": float(t.linear.x), "vy": float(t.linear.y),
            "wz": float(t.angular.z),
        }).encode()
        self.sock.sendto(pkt, UDP_ADDR)
        self.n += 1
        now = time.monotonic()
        if now - self.last_log > 2.0:
            self.last_log = now
            self.get_logger().info(
                f"#{self.n}  pos=({p.x:+.2f},{p.y:+.2f})"
                f"  yaw={math.degrees(yaw):+.1f}도")

    def health(self):
        if self.n == 0:
            self.get_logger().warn(
                "수신 0건 — 로봇 전원? tapenv 진입? 토픽명 확인: "
                "ros2 topic list --no-daemon | grep odom")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", default="/state_estimator/odom_pelvis")
    args, _ = ap.parse_known_args()

    rclpy.init()
    node = TapRos(args.topic)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()


if __name__ == "__main__":
    main()
