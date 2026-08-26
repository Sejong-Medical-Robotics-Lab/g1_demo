#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_nav2_full.launch.py — [평소 터미널] B안 본체 올인원

한 방에 뜨는 것:
  · g1_odom_relay  (UDP:17777 → /odom + TF)
  · g1_joint_relay (UDP:17778 → /joint_states)
  · G1 모형 (정적TF z=0.782 + robot_state_publisher, 실관절)
  · 기존 g1_nav2_odomB.launch.py 전체 (map/AMCL/Nav2/RViz)

터미널 4개 체제:
  1) tapenv:  source ~/g1_real/tapenv.sh → bash ~/g1_real/run_taps.sh
  2) g1ros:   python3 ~/g1_real/g1_cmdvel_bridge.py --iface $G1_IFACE
  3) 평소:    ros2 launch ~/g1_real/g1_nav2_full.launch.py     ← 이 파일
  4) 예비:    set_pose.sh / clearmap.sh

모형 빼고 가볍게: model:=false
"""
import importlib.util
import os

from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, ExecuteProcess,
                            IncludeLaunchDescription)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

HERE = os.path.expanduser("~/g1_real")

# 모형 launch 의 URDF 로더 재사용 (파일명에 점이 있어 경로 로딩)
_spec = importlib.util.spec_from_file_location(
    "g1_model_mod", os.path.join(HERE, "g1_model_display.launch.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def generate_launch_description():
    name, desc = _mod.load_urdf_text()
    root = _mod.root_link(desc)
    print(f"[full] URDF: {name} (루트: {root})")
    model = LaunchConfiguration("model")

    return LaunchDescription([
        DeclareLaunchArgument("model", default_value="true"),

        # ── 릴레이 2종 (심장) ──
        ExecuteProcess(cmd=["python3", os.path.join(HERE, "g1_odom_relay.py")],
                       name="odom_relay", output="screen"),
        ExecuteProcess(cmd=["python3", os.path.join(HERE, "g1_joint_relay.py")],
                       name="joint_relay", output="screen"),

        # ── G1 모형 (실관절 — joint_relay 가 /joint_states 공급) ──
        Node(package="tf2_ros", executable="static_transform_publisher",
             arguments=["--z", "0.782",
                        "--frame-id", "base_link", "--child-frame-id", root],
             condition=IfCondition(model), output="screen"),
        Node(package="robot_state_publisher", executable="robot_state_publisher",
             parameters=[{"robot_description": desc}],
             condition=IfCondition(model), output="screen"),

        # ── 검증본 Nav2 스택 통째로 ──
        IncludeLaunchDescription(PythonLaunchDescriptionSource(
            os.path.join(HERE, "g1_nav2_odomB.launch.py"))),
    ])
