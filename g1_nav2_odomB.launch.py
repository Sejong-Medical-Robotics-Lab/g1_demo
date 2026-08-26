#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_nav2_odomB.launch.py — B안: 내장 오도메트리 기반 자율주행

기존(g1_nav2_localize.launch.py)과의 차이 하나:
    오도메트리를 FAST-LIO(라이다 10Hz)가 아니라 **로봇 내장
    오도메트리**(관절+IMU, 고주파)에서 받는다. 라이다 파이프라인의
    지연이 위치추정에 전파되던 구조를 뿌리에서 제거한다.
    FAST-LIO 는 이 구성에서 아예 안 띄운다.

프레임:
    map ──(AMCL)──> odom ──(g1_odom_bridge)──> base_link ──(static)──> livox_frame

실행 순서 (터미널 4개):
    lidar → ros2 launch livox_ros_driver2 pc2_MID360s_launch.py
            ※ PointCloud2 출력판 — 만드는 법은 ODOM_B_GUIDE.md 1단계
    g1    → python3 ~/g1_real/g1_odom_bridge.py --iface $G1_IFACE
    g1ros → python3 ~/g1_real/g1_cmdvel_bridge.py --iface $G1_IFACE
    slam  → ros2 launch ~/g1_real/g1_nav2_odomB.launch.py
    → RViz 에서 초기 위치 (안 되면 set_pose.sh)
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    home = os.path.expanduser("~")
    default_params = os.path.join(home, "g1_real", "nav2_g1_odomB.yaml")

    params_file = LaunchConfiguration("params_file")
    use_rviz = LaunchConfiguration("rviz")

    nav2_bringup_dir = get_package_share_directory("nav2_bringup")
    # 전용 화면 설정(모형 자동표시·TF축 3개만) 우선, 없으면 nav2 기본
    _custom_rviz = os.path.expanduser("~/g1_real/g1_demo.rviz")
    default_rviz = _custom_rviz if os.path.exists(_custom_rviz) \
        else os.path.join(nav2_bringup_dir, "rviz", "nav2_default_view.rviz")

    return LaunchDescription([
        DeclareLaunchArgument("params_file", default_value=default_params),
        DeclareLaunchArgument("rviz", default_value="true"),

        # ── TF: base_link → livox_frame (정적) ───────────────────────
        # 라이다는 머리(골반 기준 약 +0.50m 위)에 있다.
        # z 값은 실측으로 보정: 로봇 세워두고 RViz 에서 스캔의 벽
        # 높이가 이상하면 조정. 2D 내비에선 z 오차는 큰 문제 아님 —
        # 중요한 건 yaw(회전) 정합이다.
        #
        # ★ 첫 실행 때 RViz 확인 필수: 로봇이 복도를 보고 있을 때
        #   스캔의 좌우가 실제와 같은가? 거울처럼 뒤집혀 보이면
        #   아래 arguments 를 roll 180 판으로 교체:
        #   ["--x","0.02","--z","0.50","--roll","3.14159",
        #    "--frame-id","base_link","--child-frame-id","livox_frame"]
        Node(
            package="tf2_ros", executable="static_transform_publisher",
            name="base_to_livox",
            arguments=["--x", "0.02", "--z", "0.50",
                       "--frame-id", "base_link",
                       "--child-frame-id", "livox_frame"],
        ),

        # ── 3D 점구름(원시) → 2D 스캔 ────────────────────────────────
        # FAST-LIO 를 안 거치므로 라이다 원시 출력(PointCloud2)을 바로
        # 납작하게 만든다. 왜곡보정(deskew)이 없어지지만 0.12m/s
        # 저속에선 프레임당 1~2cm 수준 — AMCL 허용 범위.
        Node(
            package="pointcloud_to_laserscan",
            executable="pointcloud_to_laserscan_node",
            name="pointcloud_to_laserscan",
            remappings=[("cloud_in", "/livox/lidar"),
                        ("scan", "/scan")],
            parameters=[{
                "target_frame": "base_link",
                "transform_tolerance": 0.2,
                # base_link(골반, 바닥 위 ~0.75m) 기준 높이 구간.
                # 기존 head 기준 -1.0~0.3 과 같은 절대 구간(바닥 위
                # 0.25~1.55m)이 되도록 환산한 값.
                "min_height": -0.50,
                "max_height": 0.80,
                "angle_min": -3.14159,
                "angle_max": 3.14159,
                "angle_increment": 0.0087,
                "scan_time": 0.1,
                "range_min": 0.60,
                "range_max": 15.0,
                "use_inf": True,
                "inf_epsilon": 1.0,
            }],
        ),

        # ── 지도 서버 + AMCL ─────────────────────────────────────────
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(nav2_bringup_dir, "launch", "localization_launch.py")),
            launch_arguments={
                "use_sim_time": "false",
                "params_file": params_file,
                "autostart": "true",
                "use_composition": "False",
            }.items(),
        ),

        # ── Nav2 ─────────────────────────────────────────────────────
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

        # ── RViz ─────────────────────────────────────────────────────
        Node(
            package="rviz2", executable="rviz2", name="rviz2",
            arguments=["-d", default_rviz],
            condition=IfCondition(use_rviz),
            output="log",
        ),
    ])
