#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_nav2_localize.launch.py — 사전 지도 + AMCL 기반 자율주행.

주행 중에 지도까지 만드는 방식(g1_nav2.launch.py)은 휴머노이드에서 불안정했다.
보행 진동으로 위치 추정이 흔들리고, 지도와 위치가 동시에 어긋나면서
로봇이 엉뚱한 방향으로 갔다.

이 launch 는 그것을 두 단계로 나눈다.

    1단계) 미리 걸어다니며 지도를 만들어 저장한다  (아래 "사전 준비")
    2단계) 그 지도를 고정해두고 AMCL 이 위치만 찾는다  ← 이 파일

지도가 변하지 않으므로 **오차가 누적되지 않는다.** 바퀴 로봇에서 오래
검증된 방식이고, 훨씬 안정적이다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
프레임 구조
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    map ──(AMCL 이 보정)──> camera_init ──(FAST-LIO)──> body ──> base_link
     ↑                          ↑
   고정 지도                오도메트리(단기 정확)

FAST-LIO 는 **오도메트리 역할만** 한다. 짧은 시간 동안의 상대 이동은
정확하지만 길게 가면 드리프트가 쌓인다. 그 드리프트를 AMCL 이 고정
지도와 대조해 계속 보정한다. 역할 분담이 명확하다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
사전 준비 — 지도 만들기 (한 번만)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
① LiDAR + FAST-LIO 를 띄우고 로봇을 **천천히** 걷게 하며 공간을 돈다
     lidar → ros2 launch livox_ros_driver2 msg_MID360s_launch.py
     slam  → ros2 launch fast_lio mapping.launch.py config_file:=mid360s.yaml

② 지도가 잘 나왔으면 저장
     slam  → savemap            # → ~/g1_real/maps/lab.pcd

③ 2D 로 변환
     python3 ~/g1_real/pcd_to_map.py ~/g1_real/maps/lab.pcd \\
         -o ~/g1_real/maps/lab_2d --z-min -1.2 --z-max -0.2

④ 이미지로 확인 — 벽이 검은 선, 통로가 흰색이면 정상
     eog ~/g1_real/maps/lab_2d.pgm

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
실행 — 자율주행
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
① 로봇을 FSM 501 로 올린다. **지도를 만들 때 출발했던 자리 근처에 둔다.**
     g1 → python3 g1_stand_test.py --iface $G1_IFACE

② LiDAR
     lidar → ros2 launch livox_ros_driver2 msg_MID360s_launch.py

③ FAST-LIO (오도메트리 역할)
     slam  → ros2 launch fast_lio mapping.launch.py config_file:=mid360s.yaml

④ 브리지 ← 로봇을 실제로 움직이는 것은 이 노드. **끄면 비상 정지.**
     g1ros → python3 g1_cmdvel_bridge.py --iface $G1_IFACE

⑤ 이 launch
     slam  → ros2 launch /home/hong/g1_real/g1_nav2_localize.launch.py

⑥ RViz 에서 **초기 위치를 알려준다** ← 이 방식에서 가장 중요한 절차
     Fixed Frame 을 map 으로
     "2D Pose Estimate" 로 로봇의 실제 위치·방향을 클릭·드래그
     → AMCL 의 화살표 뭉치가 로봇 주변으로 모이면 성공

⑦ "2D Goal Pose" 로 목표 지점 지정

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⑥ 을 건너뛰면 로봇은 자기가 어디 있는지 모른 채 움직인다. 반드시 한다.
지도를 만들 때와 같은 자리에서 시작하면 초기 위치를 잡기 훨씬 쉽다.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    home = os.path.expanduser("~")
    default_params = os.path.join(home, "g1_real", "nav2_g1_localize.yaml")
    default_map = os.path.join(home, "g1_real", "maps", "lab_2d.yaml")

    params_file = LaunchConfiguration("params_file")
    map_file = LaunchConfiguration("map")
    use_rviz = LaunchConfiguration("rviz")

    nav2_bringup_dir = get_package_share_directory("nav2_bringup")
    # Nav2 가 제공하는 기본 RViz 설정. Map / LaserScan / particlecloud /
    # 경로 표시와 목표 지정 도구가 미리 세팅되어 있어 직접 Add 할 필요가 없다.
    default_rviz = os.path.join(nav2_bringup_dir, "rviz", "nav2_default_view.rviz")

    from launch.conditions import IfCondition
    from launch_ros.actions import Node

    return LaunchDescription([
        DeclareLaunchArgument("params_file", default_value=default_params),
        DeclareLaunchArgument("map", default_value=default_map,
                              description="사전에 만든 2D 지도(.yaml)"),
        DeclareLaunchArgument("rviz", default_value="true"),

        # ── TF: body → base_link (항등) ──────────────────────────────
        # FAST-LIO 는 IMU 기준 프레임을 body 로 낸다. Nav2 관례상 base_link 를
        # 쓰므로 이름만 이어준다.
        #
        # ※ map → camera_init 는 여기서 발행하지 않는다. **AMCL 이 발행한다.**
        #   그것이 이 구성의 핵심이다 — 고정 지도에 맞춰 오도메트리 드리프트를
        #   계속 보정하는 역할이다.
        Node(
            package="tf2_ros", executable="static_transform_publisher",
            name="body_to_base_link",
            arguments=["--frame-id", "body", "--child-frame-id", "base_link"],
        ),

        # ── 3D 포인트 → 2D 스캔 ──────────────────────────────────────
        # AMCL 과 costmap 이 모두 이 /scan 을 쓴다.
        Node(
            package="pointcloud_to_laserscan",
            executable="pointcloud_to_laserscan_node",
            name="pointcloud_to_laserscan",
            remappings=[("cloud_in", "/cloud_registered_body"),
                        ("scan", "/scan")],
            parameters=[{
                "target_frame": "base_link",
                "transform_tolerance": 0.05,
                # LiDAR 는 머리(≈1.3m)에 있다. base_link 기준 높이 구간이며,
                # pcd_to_map.py 의 --z-min/--z-max 와 **같은 구간**을 봐야
                # AMCL 이 지도와 스캔을 제대로 대조할 수 있다.
                "min_height": -1.0,
                "max_height": 0.3,
                "angle_min": -3.14159,
                "angle_max": 3.14159,
                "angle_increment": 0.0087,
                "scan_time": 0.1,
                # 로봇 자기 몸과 바로 옆을 지나는 사람을 제외한다.
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
                "map": map_file,
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
        # nav2_default_view.rviz 에는 2D Pose Estimate / 2D Goal Pose 도구와
        # Map·LaserScan·particlecloud 표시가 이미 들어 있다.
        # 끄려면 rviz:=false
        Node(
            package="rviz2", executable="rviz2", name="rviz2",
            arguments=["-d", default_rviz],
            condition=IfCondition(use_rviz),
            output="log",
        ),
    ])
