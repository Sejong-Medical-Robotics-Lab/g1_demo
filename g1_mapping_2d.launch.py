#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_mapping_2d.launch.py — 2D 지도 작성 (slam_toolbox + FAST-LIO 오도메트리).

FAST-LIO 만으로 지도를 만들면 **루프 클로저가 없어** 한 번 어긋난 위치를
되돌릴 방법이 없다. 휴머노이드 보행 진동 때문에 회전 구간에서 특히 잘
어긋나고, 그 오차가 그대로 쌓여 지도가 사방으로 뻗어나간다.

slam_toolbox 를 얹으면 두 가지가 해결된다.

  ① **루프 클로저** — 이미 지나온 곳을 다시 보면 어긋난 위치를 되돌린다
  ② **2D 투영** — z 축이 사라지므로 상하 진동이 위치 추정에 개입하지 못한다

그리고 결과물이 **Nav2 가 그대로 쓰는 점유격자**라, PCD → 2D 변환 단계가
통째로 사라진다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
역할 분담
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    FAST-LIO      : 오도메트리 (camera_init → body).
                    짧은 시간의 상대 이동은 정확하지만 길게 가면 드리프트
    slam_toolbox  : 2D 스캔매칭 + 루프 클로저.
                    map → camera_init 을 발행해 그 드리프트를 보정

    map ──(slam_toolbox)──> camera_init ──(FAST-LIO)──> body ──> base_link

FAST-LIO 의 3D 포인트클라우드도 계속 나오므로, RViz 에 2D 지도와 3D 를
동시에 띄울 수 있다. 발표용 3D 화면을 포기하지 않아도 된다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
사전 설치
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    sudo apt install -y ros-jazzy-slam-toolbox ros-jazzy-pointcloud-to-laserscan

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
실행 — 터미널 4~5개
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
① 로봇을 FSM 501 로
     g1    → python3 g1_stand_test.py --iface $G1_IFACE
     **출발 지점을 바닥에 표시해 둔다.** 나중에 주행할 때 같은 자리에서
     시작하면 초기 위치를 잡기 쉽다.

② LiDAR
     lidar → ros2 launch livox_ros_driver2 msg_MID360s_launch.py

③ FAST-LIO — 오도메트리 제공 (품질 설정)
     slam  → ros2 launch fast_lio mapping.launch.py \\
                 config_file:=mid360s_mapping.yaml

④ 이 launch (2D SLAM + RViz)
     slam  → ros2 launch /home/hong/g1_real/g1_mapping_2d.launch.py

⑤ 로봇 조종 — 조이스틱이 편하다. 코드로 한다면:
     g1ros → python3 g1_cmdvel_bridge.py --iface $G1_IFACE
     그리고 다른 터미널에서 /cmd_vel 발행

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
걷는 방법 — 지도 품질을 좌우한다
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
· **회전을 원호로.** 제자리 회전이 위치 추정을 가장 크게 흔든다.
  멈춰서 돌지 말고 전진하면서 완만하게 돌아간다.
      ros2 topic pub -r 10 /cmd_vel geometry_msgs/msg/Twist \\
          "{linear: {x: 0.12}, angular: {z: 0.1}}"
· **천천히, 끊김 없이.** vx 0.15 이하. 급출발·급정지가 IMU 를 흔든다.
· **출발점으로 되돌아온다.** ← 루프 클로저가 작동하는 순간이다.
  한 바퀴 돌아 처음 자리로 오면 쌓인 오차가 한 번에 보정된다.
  RViz 에서 지도가 살짝 "튕기며" 정렬되는 것이 보인다.
· 사람이 없는 시간에. 움직이는 물체가 정합을 방해한다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
저장
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
지도가 깔끔하면(벽이 한 겹으로 보이면):

    slam
    ros2 run nav2_map_server map_saver_cli -f ~/g1_real/maps/lab_2d

    → lab_2d.pgm + lab_2d.yaml 생성. 이것을 주행에 그대로 쓴다.
      (pcd_to_map.py 는 이제 필요 없다)

3D PCD 도 함께 남기고 싶으면 FAST-LIO 쪽에서 따로:
    savemap
"""
import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    use_rviz = LaunchConfiguration("rviz")
    rviz_cfg = LaunchConfiguration("rviz_config")

    # Fixed Frame(map), Map(/map), LaserScan(/scan), Odometry 가 미리 설정된
    # 파일. 매번 손으로 Add 하지 않아도 된다.
    default_rviz = os.path.join(os.path.expanduser("~"), "g1_real",
                                "g1_mapping.rviz")

    return LaunchDescription([
        DeclareLaunchArgument("rviz", default_value="true"),
        DeclareLaunchArgument("rviz_config", default_value=default_rviz),

        # ── TF: body → base_link (항등) ──────────────────────────────
        # FAST-LIO 는 IMU 기준 프레임을 body 로 낸다. ROS 관례상 base_link 를
        # 쓰므로 이름만 이어준다.
        #
        # ※ map → camera_init 는 여기서 발행하지 않는다. **slam_toolbox 가
        #   발행한다.** 그것이 이 구성의 핵심이다 — FAST-LIO 의 드리프트를
        #   루프 클로저로 계속 보정하는 역할이다.
        Node(
            package="tf2_ros", executable="static_transform_publisher",
            name="body_to_base_link",
            arguments=["--frame-id", "body", "--child-frame-id", "base_link"],
        ),

        # ── 3D 포인트 → 2D 스캔 ──────────────────────────────────────
        Node(
            package="pointcloud_to_laserscan",
            executable="pointcloud_to_laserscan_node",
            name="pointcloud_to_laserscan",
            remappings=[("cloud_in", "/cloud_registered_body"),
                        ("scan", "/scan")],
            parameters=[{
                "target_frame": "base_link",
                "transform_tolerance": 0.05,
                # base_link(=LiDAR 위치, 바닥에서 약 1.3m) 기준 높이 구간.
                # 바닥과 천장을 빼고 벽·기둥·가구가 잡히는 띠만 쓴다.
                #   너무 넓게 잡으면 바닥이 장애물로 찍힌다
                #   너무 좁게 잡으면 벽이 안 잡혀 정합이 안 된다
                "min_height": -1.0,
                "max_height": 0.3,
                "angle_min": -3.14159,
                "angle_max": 3.14159,
                "angle_increment": 0.0087,      # 0.5도
                "scan_time": 0.1,
                # 로봇 자기 몸(어깨·팔)과 바로 옆을 지나는 사람을 제외한다.
                "range_min": 0.60,
                "range_max": 20.0,
                "use_inf": True,
                "inf_epsilon": 1.0,
            }],
        ),

        # ── slam_toolbox — 2D SLAM + 루프 클로저 ─────────────────────
        Node(
            package="slam_toolbox",
            executable="async_slam_toolbox_node",
            name="slam_toolbox",
            output="screen",
            parameters=[{
                "use_sim_time": False,

                # FAST-LIO 의 원점을 오도메트리 프레임으로 삼는다.
                # slam_toolbox 가 map → odom_frame 을 발행해 보정한다.
                "odom_frame": "camera_init",
                "map_frame": "map",
                "base_frame": "base_link",
                "scan_topic": "/scan",
                "mode": "mapping",

                "resolution": 0.05,             # 격자 5cm
                "max_laser_range": 20.0,
                "minimum_time_interval": 0.2,
                "transform_timeout": 0.5,       # 보행 진동을 감안해 느슨하게
                "tf_buffer_duration": 30.0,
                "map_update_interval": 1.0,
                "enable_interactive_mode": True,

                # ── 갱신 빈도 ────────────────────────────────────────
                # 촘촘히 갱신할수록 정확하지만 계산이 는다.
                # 휴머노이드는 느리게 움직이므로 이 정도면 충분하다.
                "minimum_travel_distance": 0.2,
                "minimum_travel_heading": 0.2,

                # ── 스캔 매칭 ────────────────────────────────────────
                "use_scan_matching": True,
                "use_scan_barycenter": True,
                "scan_buffer_size": 20,
                "scan_buffer_maximum_scan_distance": 20.0,
                "link_match_minimum_response_fine": 0.1,
                "link_scan_maximum_distance": 3.0,

                # 오도메트리를 얼마나 믿을지. 보행은 미끄러짐과 흔들림이
                # 크므로 페널티를 낮춰(=1.0 에 가깝게) 스캔 정합 쪽에
                # 더 의존하게 한다.
                "distance_variance_penalty": 0.3,
                "angle_variance_penalty": 0.5,
                "minimum_angle_penalty": 0.9,
                "minimum_distance_penalty": 0.5,
                "use_response_expansion": True,

                # ── ★ 루프 클로저 — 이것 때문에 slam_toolbox 를 쓴다 ──
                # 이미 지나온 곳을 다시 보면 쌓인 오차를 되돌린다.
                # FAST-LIO 에는 없는 기능이다.
                "do_loop_closing": True,
                "loop_search_maximum_distance": 5.0,
                "loop_match_minimum_chain_size": 8,
                "loop_match_maximum_variance_coarse": 3.0,
                "loop_match_minimum_response_coarse": 0.35,
                "loop_match_minimum_response_fine": 0.45,

                "correlation_search_space_dimension": 0.5,
                "correlation_search_space_resolution": 0.01,
                "correlation_search_space_smear_deviation": 0.1,
                "loop_search_space_dimension": 8.0,
                "loop_search_space_resolution": 0.05,
                "loop_search_space_smear_deviation": 0.03,
            }],
        ),

        # ── ★ 라이프사이클 활성화 ────────────────────────────────────
        # slam_toolbox 는 라이프사이클 노드다. 프로세스가 떠도 그것만으로는
        # 동작하지 않는다 — configure → activate 를 거쳐야 비로소 /scan 을
        # 구독하고 /map 을 발행한다.
        #
        # 이걸 빠뜨리면 노드는 멀쩡히 살아 있는데 아무 일도 일어나지 않고
        # 에러도 안 난다. (RViz 에는 "Frame [map] does not exist" 만 뜬다)
        Node(
            package="nav2_lifecycle_manager",
            executable="lifecycle_manager",
            name="lifecycle_manager_slam",
            output="screen",
            parameters=[{
                "use_sim_time": False,
                "autostart": True,
                "node_names": ["slam_toolbox"],
            }],
        ),

        Node(
            package="rviz2", executable="rviz2", name="rviz2",
            arguments=["-d", rviz_cfg],
            condition=IfCondition(use_rviz),
            output="log",
        ),
    ])
