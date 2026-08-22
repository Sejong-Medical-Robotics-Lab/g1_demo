#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_nav2.launch.py — G1 자율주행 (Nav2 + FAST-LIO 오도메트리).

    FAST-LIO ── camera_init→body TF, /cloud_registered_body
        ↓
    pointcloud_to_laserscan ── /scan
        ↓
    Nav2 (costmap → planner → controller) ── /cmd_vel
        ↓
    g1_cmdvel_bridge ── SetVelocity() ── G1

프레임 사슬:

    map ──(static, identity)──> camera_init ──(FAST-LIO)──> body
                                                             │
                                              (static, identity)
                                                             ↓
                                                        base_link

사전 지도(AMCL)를 쓰지 않는다. FAST-LIO 의 추정을 그대로 쓰고 costmap 은
롤링 윈도우로만 돈다. 부품이 적어 실패 지점도 적지만, 루프 클로저가 없어
장거리에서는 드리프트가 쌓인다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
실행 순서 — 터미널 4개
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
① 로봇을 FSM 501(레귤러)까지 올린다
     g1
     python3 g1_stand_test.py --iface $G1_IFACE

② LiDAR (CustomMsg)
     lidar
     ros2 launch livox_ros_driver2 msg_MID360s_launch.py

③ FAST-LIO
     slam
     ros2 launch fast_lio mapping.launch.py config_file:=mid360s.yaml

④ cmd_vel 브리지 ← 로봇을 실제로 움직이는 것은 이 노드다
     g1
     source /opt/ros/jazzy/setup.bash
     export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
     python3 g1_cmdvel_bridge.py --iface $G1_IFACE

⑤ Nav2 (이 파일)
     slam
     ros2 launch ~/g1_real/g1_nav2.launch.py

목표 지점 주기: RViz 의 "2D Goal Pose" 버튼. Fixed Frame 을 map 으로.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

안전:
  · 브리지(④)를 끄면 로봇은 0.5초 안에 멈춘다. **이것이 비상 정지다.**
  · 브리지의 clamp 가 Nav2 설정보다 우선한다. Nav2 파라미터가 잘못돼도
    vx 0.3 / vyaw 0.4 를 넘지 않는다.
  · 첫 시도는 사람이 적은 곳에서, 목표를 2~3m 앞으로 짧게 준다.
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    params_file = LaunchConfiguration("params_file")
    use_bridge_topic = LaunchConfiguration("cmd_vel_topic")

    default_params = os.path.join(os.path.expanduser("~"), "g1_real", "nav2_g1.yaml")
    nav2_bringup_dir = get_package_share_directory("nav2_bringup")

    return LaunchDescription([
        DeclareLaunchArgument("params_file", default_value=default_params),
        DeclareLaunchArgument("cmd_vel_topic", default_value="/cmd_vel"),

        # ── TF: map → camera_init (항등) ─────────────────────────────
        # 사전 지도가 없으므로 FAST-LIO 의 원점을 그대로 map 으로 삼는다.
        Node(
            package="tf2_ros", executable="static_transform_publisher",
            name="map_to_odom",
            arguments=["--frame-id", "map", "--child-frame-id", "camera_init"],
        ),

        # ── TF: body → base_link (항등) ──────────────────────────────
        # FAST-LIO 는 IMU 기준 프레임을 body 로 낸다. Nav2 관례상 base_link 를
        # 쓰므로 이름만 이어준다. 실제 로봇 발 위치와의 높이 차이는 2D 내비에
        # 영향을 주지 않아 0 으로 둔다.
        Node(
            package="tf2_ros", executable="static_transform_publisher",
            name="body_to_base_link",
            arguments=["--frame-id", "body", "--child-frame-id", "base_link"],
        ),

        # ── 3D 포인트 → 2D 스캔 ──────────────────────────────────────
        # FAST-LIO 가 body 프레임으로 내보내는 정합된 스캔을 쓴다
        # (config 의 scan_bodyframe_pub_en: true).
        # 높이 구간은 base_link(=LiDAR 높이) 기준이다.
        Node(
            package="pointcloud_to_laserscan",
            executable="pointcloud_to_laserscan_node",
            name="pointcloud_to_laserscan",
            remappings=[("cloud_in", "/cloud_registered_body"),
                        ("scan", "/scan")],
            parameters=[{
                "target_frame": "base_link",
                "transform_tolerance": 0.05,
                # LiDAR 는 머리(≈1.3m)에 있다. 바닥·천장을 빼고 몸통 높이 띠만
                # 장애물로 본다. 낮은 장애물을 놓치면 이 범위를 넓힌다.
                "min_height": -1.1,
                "max_height": 0.2,
                "angle_min": -3.14159,
                "angle_max": 3.14159,
                "angle_increment": 0.0087,     # 0.5도
                "scan_time": 0.1,
                "range_min": 0.30,
                "range_max": 15.0,
                "use_inf": True,
                "inf_epsilon": 1.0,
            }],
        ),

        # ── Nav2 ─────────────────────────────────────────────────────
        # 사전 지도가 없으므로 map_server / AMCL 없이 navigation 만 띄운다.
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(nav2_bringup_dir, "launch", "navigation_launch.py")),
            launch_arguments={
                "use_sim_time": "false",
                "params_file": params_file,
                "autostart": "true",
                "use_composition": "False",
            }.items(),
        ),
    ])
