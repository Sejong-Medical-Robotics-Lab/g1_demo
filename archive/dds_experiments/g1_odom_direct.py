#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_odom_direct.py — [평소 터미널] 로봇 오도메트리 직결 어댑터

도메인 통일(0) 후 평소 세계(FastDDS)에서 로봇 토픽이 직접 보임이
확인됨 → tap/relay(UDP 우회) 없이 이 노드 하나로:

    /state_estimator/odom_pelvis (로봇, 51Hz)
        → /odom 재발행 + TF(odom→base_link)

사용 (평소 터미널, venv 없이):
    source /opt/ros/jazzy/setup.bash    # 또는 평소 별칭
    python3 ~/g1_real/g1_odom_direct.py
확인:
    ros2 topic hz /odom
    ros2 run tf2_ros tf2_echo odom base_link
"""
import math

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from nav_msgs.msg import Odometry
from geometry_msgs.msg import TransformStamped
from tf2_ros import TransformBroadcaster

SRC_TOPIC = "/state_estimator/odom_pelvis"


class OdomDirect(Node):
    def __init__(self):
        super().__init__("g1_odom_direct")
        self.pub = self.create_publisher(Odometry, "/odom", 10)
        self.tf_bc = TransformBroadcaster(self)
        self.n = 0
        qos = QoSProfile(depth=10,
                         reliability=ReliabilityPolicy.BEST_EFFORT,
                         history=HistoryPolicy.KEEP_LAST)
        self.sub = self.create_subscription(Odometry, SRC_TOPIC, self.cb, qos)
        self.get_logger().info(f"{SRC_TOPIC} 직결 → /odom + TF(odom→base_link)")
        self.create_timer(5.0, self.health)

    def cb(self, m: Odometry):
        now = self.get_clock().now().to_msg()
        p = m.pose.pose.position
        o = m.pose.pose.orientation
        # yaw 만 투영 (보행 중 몸 기울어짐이 2D 매칭을 오염시키지 않게)
        yaw = math.atan2(2.0 * (o.w * o.z + o.x * o.y),
                         1.0 - 2.0 * (o.y * o.y + o.z * o.z))
        qz, qw = math.sin(yaw / 2.0), math.cos(yaw / 2.0)

        out = Odometry()
        out.header.stamp = now
        out.header.frame_id = "odom"
        out.child_frame_id = "base_link"
        out.pose.pose.position.x = p.x
        out.pose.pose.position.y = p.y
        out.pose.pose.orientation.z = qz
        out.pose.pose.orientation.w = qw
        out.twist = m.twist
        for i in (0, 7, 14, 21, 28, 35):
            out.pose.covariance[i] = 0.01
            out.twist.covariance[i] = 0.01
        self.pub.publish(out)

        t = TransformStamped()
        t.header.stamp = now
        t.header.frame_id = "odom"
        t.child_frame_id = "base_link"
        t.transform.translation.x = p.x
        t.transform.translation.y = p.y
        t.transform.rotation.z = qz
        t.transform.rotation.w = qw
        self.tf_bc.sendTransform(t)

        self.n += 1
        if self.n % 250 == 1:
            self.get_logger().info(
                f"#{self.n}  pos=({p.x:+.2f},{p.y:+.2f})  yaw={math.degrees(yaw):+.1f}도")

    def health(self):
        if self.n == 0:
            self.get_logger().warn(
                "수신 0건 — 로봇 전원? 도메인 0 확인? "
                "직결이 안 되는 환경이면 tap/relay 구조로 (RELAY_GUIDE)")


def main():
    rclpy.init()
    node = OdomDirect()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()


if __name__ == "__main__":
    main()
