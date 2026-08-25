#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_odom_relay.py — [일반 ROS 터미널] UDP 수신 → /odom + TF(odom→base_link)

g1_odom_tap.py(3.11 쪽)가 쏘는 UDP JSON 을 받아 ROS 로 발행한다.
sdk2py 를 전혀 안 쓰므로 **venv 없이** 시스템 ROS 만으로 돈다 —
환경 충돌이 원천적으로 없다.

사용 (venv 활성화 없이, 새 터미널에서):
    python3 ~/g1_real/g1_odom_relay.py
확인:
    ros2 topic hz /odom
    ros2 run tf2_ros tf2_echo odom base_link
"""
import json
import math
import select
import socket

import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from geometry_msgs.msg import TransformStamped
from tf2_ros import TransformBroadcaster

UDP_PORT = 17777


class OdomRelay(Node):
    def __init__(self):
        super().__init__("g1_odom_relay")
        self.pub = self.create_publisher(Odometry, "/odom", 10)
        self.tf_bc = TransformBroadcaster(self)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", UDP_PORT))
        self.sock.setblocking(False)
        self.n = 0
        self.get_logger().info(
            f"UDP:{UDP_PORT} 대기 → /odom + TF(odom→base_link) 발행. "
            "tap(3.11쪽)이 떠 있어야 데이터가 온다")
        self.timer = self.create_timer(0.005, self.poll)   # 200Hz 폴링
        self.warn_timer = self.create_timer(5.0, self.health)

    def poll(self):
        # 밀린 패킷은 다 비우고 마지막 것만 발행 (최신 우선)
        latest = None
        while True:
            r, _, _ = select.select([self.sock], [], [], 0)
            if not r:
                break
            data, _ = self.sock.recvfrom(512)
            latest = data
        if latest is None:
            return
        try:
            d = json.loads(latest.decode())
        except Exception:
            return

        now = self.get_clock().now().to_msg()
        qz, qw = math.sin(d["yaw"] / 2.0), math.cos(d["yaw"] / 2.0)

        odom = Odometry()
        odom.header.stamp = now
        odom.header.frame_id = "odom"
        odom.child_frame_id = "base_link"
        odom.pose.pose.position.x = d["x"]
        odom.pose.pose.position.y = d["y"]
        odom.pose.pose.orientation.z = qz
        odom.pose.pose.orientation.w = qw
        odom.twist.twist.linear.x = d["vx"]
        odom.twist.twist.linear.y = d["vy"]
        odom.twist.twist.angular.z = d["wz"]
        for i in (0, 7, 14, 21, 28, 35):
            odom.pose.covariance[i] = 0.01
            odom.twist.covariance[i] = 0.01
        self.pub.publish(odom)

        t = TransformStamped()
        t.header.stamp = now
        t.header.frame_id = "odom"
        t.child_frame_id = "base_link"
        t.transform.translation.x = d["x"]
        t.transform.translation.y = d["y"]
        t.transform.rotation.z = qz
        t.transform.rotation.w = qw
        self.tf_bc.sendTransform(t)
        self.n += 1

    def health(self):
        if self.n == 0:
            self.get_logger().warn("아직 수신 0건 — tap(3.11쪽) 실행/로봇 전원 확인")
        else:
            self.get_logger().info(f"정상 — 누적 {self.n}건")


def main():
    rclpy.init()
    node = OdomRelay()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()


if __name__ == "__main__":
    main()
