#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_joint_relay.py — [평소 터미널] UDP 관절각 → /joint_states 발행

g1_joint_tap.py(17778)가 보내는 29개 관절각을 받아 표준
sensor_msgs/JointState 로 발행한다. 모형 launch 를 jsp:=false 로
띄우면 이 실측 관절각이 G1 모형을 움직인다.

사용 (venv 없이):
    python3 ~/g1_real/g1_joint_relay.py
확인:
    ros2 topic hz /joint_states     # ~30Hz
"""
import json
import select
import socket

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState

UDP_PORT = 17778

# G1 29dof 모터 인덱스 순서 = URDF revolute 순서 (2026-08-26 검증)
NAMES = [
    "left_hip_pitch_joint", "left_hip_roll_joint", "left_hip_yaw_joint",
    "left_knee_joint", "left_ankle_pitch_joint", "left_ankle_roll_joint",
    "right_hip_pitch_joint", "right_hip_roll_joint", "right_hip_yaw_joint",
    "right_knee_joint", "right_ankle_pitch_joint", "right_ankle_roll_joint",
    "waist_yaw_joint", "waist_roll_joint", "waist_pitch_joint",
    "left_shoulder_pitch_joint", "left_shoulder_roll_joint",
    "left_shoulder_yaw_joint", "left_elbow_joint",
    "left_wrist_roll_joint", "left_wrist_pitch_joint", "left_wrist_yaw_joint",
    "right_shoulder_pitch_joint", "right_shoulder_roll_joint",
    "right_shoulder_yaw_joint", "right_elbow_joint",
    "right_wrist_roll_joint", "right_wrist_pitch_joint", "right_wrist_yaw_joint",
]


class JointRelay(Node):
    def __init__(self):
        super().__init__("g1_joint_relay")
        self.pub = self.create_publisher(JointState, "/joint_states", 10)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", UDP_PORT))
        self.sock.setblocking(False)
        self.n = 0
        self.get_logger().info(
            f"UDP:{UDP_PORT} → /joint_states. 모형 launch 는 jsp:=false 로!")
        self.create_timer(0.005, self.poll)
        self.create_timer(5.0, self.health)

    def poll(self):
        latest = None
        while True:
            r, _, _ = select.select([self.sock], [], [], 0)
            if not r:
                break
            data, _ = self.sock.recvfrom(1024)
            latest = data
        if latest is None:
            return
        try:
            q = json.loads(latest.decode())
        except Exception:
            return
        if len(q) != 29:
            return
        msg = JointState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.name = NAMES
        msg.position = [float(v) for v in q]
        self.pub.publish(msg)
        self.n += 1

    def health(self):
        if self.n == 0:
            self.get_logger().warn("수신 0건 — joint_tap(tapenv쪽) 실행 확인")
        else:
            self.get_logger().info(f"정상 — 누적 {self.n}건")


def main():
    rclpy.init()
    node = JointRelay()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()


if __name__ == "__main__":
    main()
