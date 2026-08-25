# tapenv.sh — "로봇을 듣는" ROS 터미널 진입 헬퍼
#
# 이 환경에서만: ros2 topic list/echo 로 로봇 토픽이 직접 보이고,
# g1_odom_tap_ros.py 가 돈다.
#
# ★ 주의: 이 터미널의 ROS 노드는 CycloneDDS 로 돌므로, 평소
#   터미널(FastDDS)의 Nav2 등과는 ROS 토픽이 서로 안 보인다.
#   그래서 tap 은 UDP 로 relay 에 넘기는 구조다 — relay 는
#   평소 터미널에서 돌린다.
#
# 사용:  source ~/g1_real/tapenv.sh   (venv 활성화 없이!)

source /opt/ros/jazzy/setup.bash
source ~/uni_ros2_ws/install/setup.bash

export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI="file://$HOME/g1_real/cyclonedds_g1.xml"

IFACE=$(grep -o 'name="[^"]*"' ~/g1_real/cyclonedds_g1.xml | head -1 | cut -d'"' -f2)
echo "  [tapenv] RMW=cyclonedds, iface=${IFACE}"
echo "  [tapenv] 확인: ros2 topic list | grep -Ei 'odom|state'"
