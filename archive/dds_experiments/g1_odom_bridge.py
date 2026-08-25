#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_odom_bridge.py — G1 내장 오도메트리 → ROS /odom + TF(odom→base_link)

왜 이게 필요한가 (2026-08-25 결론):
    기존에는 FAST-LIO(라이다 10Hz)가 오도메트리를 겸했다. 그래서
    라이다 파이프라인의 지연·이산성이 위치추정 전체에 전파됐고,
    회전 중 "낡은 답안으로 보정하는 툭" 현상의 토양이 됐다.
    로봇 컨트롤러는 관절+IMU 로 자체 오도메트리를 고주파로 이미
    계산하고 있다 — 그걸 그대로 ROS 로 흘려보내면 오도메트리가
    라이다와 분리되어 즉답이 된다. (erasers 팀 g1_ws 의
    odom_publisher.cpp 를 unitree_sdk2py 로 포팅)

좌표 처리 (erasers 방식 그대로):
    - 위치: 내장 position[0,1] (z 는 0 — 2D 내비만 쓰므로)
    - 방향: IMU 쿼터니언에서 yaw 만 뽑아 다시 만듦
      (roll/pitch 는 버림 — 보행 중 몸 기울어짐이 2D 지도 매칭을
       오염시키지 않게 하는 처리. 2D 내비에선 이게 정석)
    - 각속도: 자이로 z

사용:
    python3 g1_odom_bridge.py --iface $G1_IFACE
    # 확인: ros2 topic hz /odom   (수십 Hz 이상이면 성공)
    #       ros2 run tf2_ros tf2_echo odom base_link
"""
import argparse
import sys
import math

import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from geometry_msgs.msg import TransformStamped
from tf2_ros import TransformBroadcaster

from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
from unitree_sdk2py.idl.unitree_go.msg.dds_ import SportModeState_


class G1OdomBridge(Node):
    def __init__(self):
        super().__init__("g1_odom_bridge")
        self.odom_pub = self.create_publisher(Odometry, "/odom", 10)
        self.tf_bc = TransformBroadcaster(self)
        self.count = 0
        self.get_logger().info("내장 오도메트리 브리지 시작 — /odom, TF odom→base_link")

    def on_state(self, msg: SportModeState_):
        now = self.get_clock().now().to_msg()

        # IMU 쿼터니언 [w,x,y,z] → yaw 만 추출
        q = msg.imu_state.quaternion
        yaw = math.atan2(2.0 * (q[0] * q[3] + q[1] * q[2]),
                         1.0 - 2.0 * (q[2] * q[2] + q[3] * q[3]))
        qz, qw = math.sin(yaw / 2.0), math.cos(yaw / 2.0)

        odom = Odometry()
        odom.header.stamp = now
        odom.header.frame_id = "odom"
        odom.child_frame_id = "base_link"
        odom.pose.pose.position.x = float(msg.position[0])
        odom.pose.pose.position.y = float(msg.position[1])
        odom.pose.pose.orientation.z = qz
        odom.pose.pose.orientation.w = qw
        odom.twist.twist.linear.x = float(msg.velocity[0])
        odom.twist.twist.linear.y = float(msg.velocity[1])
        odom.twist.twist.angular.z = float(msg.imu_state.gyroscope[2])
        for i in (0, 7, 14, 21, 28, 35):
            odom.pose.covariance[i] = 0.01
            odom.twist.covariance[i] = 0.01
        self.odom_pub.publish(odom)

        t = TransformStamped()
        t.header.stamp = now
        t.header.frame_id = "odom"
        t.child_frame_id = "base_link"
        t.transform.translation.x = float(msg.position[0])
        t.transform.translation.y = float(msg.position[1])
        t.transform.rotation.z = qz
        t.transform.rotation.w = qw
        self.tf_bc.sendTransform(t)

        self.count += 1
        if self.count % 500 == 1:
            self.get_logger().info(
                f"#{self.count}  pos=({msg.position[0]:+.2f},{msg.position[1]:+.2f})"
                f"  yaw={math.degrees(yaw):+.1f}도")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iface", required=True)
    args = ap.parse_args()
    if not args.iface.strip():
        sys.exit("\n  [중단] --iface 가 비어 있습니다. 인터페이스 이름이 바뀐 것:\n"
                 "         ip link show | grep enx   → 나온 이름으로\n"
                 "         export G1_IFACE=enx...    후 재실행\n")

    ChannelFactoryInitialize(0, args.iface)
    rclpy.init()
    node = G1OdomBridge()

    sub = ChannelSubscriber("rt/odommodestate", SportModeState_)
    sub.Init()                      # 폴링 모드 — venv_dds(11.x)에서 검증된 방식

    try:
        while rclpy.ok():
            m = sub.Read(50)        # 50ms 폴링
            if m is not None:
                node.on_state(m)
            rclpy.spin_once(node, timeout_sec=0.0)
    except KeyboardInterrupt:
        pass
    node.destroy_node()


if __name__ == "__main__":
    main()
