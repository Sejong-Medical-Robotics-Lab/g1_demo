#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_model_display.launch.py — RViz 지도 위 G1 3D 모형 (colcon 빌드 불필요판)

g1_description 이 package.xml 없는 순수 URDF 배포라 ament 를 우회한다:
  1) 소스 폴더에서 URDF 직접 탐색 (29dof·손없음 우선, xacro 폴백)
  2) mesh 의 package:// 경로 → file:// 절대경로 즉석 변환 (RViz 호환)
  3) 루트 링크 자동 판별 → base_link 와 정체 결속

사용:
    ros2 launch ~/g1_real/g1_model_display.launch.py
RViz:  Add → RobotModel (Description Topic 기본값)
"""
import glob
import os
import subprocess
import xml.etree.ElementTree as ET

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

SRC = os.path.expanduser("~/uni_ros2_ws/src/unitree_ros/robots/g1_description")


def load_urdf_text():
    urdfs = sorted(glob.glob(os.path.join(SRC, "**", "*.urdf"), recursive=True))
    def score(p):
        n = os.path.basename(p).lower()
        return (("29dof" not in n), ("hand" in n or "dex" in n or "brainco" in n), len(n))
    if urdfs:
        urdfs.sort(key=score)
        path = urdfs[0]
        text = open(path).read()
    else:
        xacros = sorted(glob.glob(os.path.join(SRC, "**", "*.xacro"), recursive=True))
        if not xacros:
            raise RuntimeError(f"URDF/xacro 없음: {SRC}")
        xacros.sort(key=score)
        path = xacros[0]
        text = subprocess.check_output(["xacro", path], text=True)
    # 메시 경로: package://g1_description → file://<절대경로>
    text = text.replace("package://g1_description", "file://" + SRC)
    # 유니트리 URDF 는 상대경로(meshes/xxx.STL)를 씀 — 절대경로로
    text = text.replace('filename="meshes/', f'filename="file://{SRC}/meshes/')
    return os.path.basename(path), text


def root_link(urdf_text):
    tree = ET.fromstring(urdf_text)
    links = {l.get("name") for l in tree.iter("link")}
    children = {j.find("child").get("link") for j in tree.iter("joint")
                if j.find("child") is not None}
    roots = sorted(links - children)
    return roots[0] if roots else "pelvis"


def generate_launch_description():
    name, desc = load_urdf_text()
    root = root_link(desc)
    print(f"[g1_model] URDF: {name}  (루트 링크: {root})")

    return LaunchDescription([
        # 기본 = 실관절 모드(jsp 꺼짐). 동상 모드(관절 0도)가 필요할 때만
        # jsp:=true 로 실행 — joint_tap/relay 없이 모형만 띄우는 경우.
        DeclareLaunchArgument("jsp", default_value="false"),
        Node(package="tf2_ros", executable="static_transform_publisher",
             arguments=["--z", "0.782",          # 펠비스 서있는 높이 (URDF 다리사슬 실측)
                        "--frame-id", "base_link", "--child-frame-id", root],
             output="screen"),
        Node(package="joint_state_publisher", executable="joint_state_publisher",
             parameters=[{"rate": 5.0, "robot_description": desc}],
             condition=IfCondition(LaunchConfiguration("jsp")),
             output="screen"),
        Node(package="robot_state_publisher", executable="robot_state_publisher",
             parameters=[{"robot_description": desc}], output="screen"),
    ])
