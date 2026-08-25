#!/usr/bin/env bash
# ros_tap_setup.sh — ROS C-계층으로 로봇 듣기 준비 (한 번만, ~10분)
#
# 파이썬 DDS 바인딩(전부 로컬 불량 libddsc 오염)을 버리고,
# 배포판이 제대로 조립한 ROS 의 CycloneDDS C 계층으로 로봇 토픽을
# 직접 듣는다 — erasers 팀이 실제로 쓰는 방식.
#
# 사용:  bash ~/g1_real/ros_tap_setup.sh

set -e
source /opt/ros/jazzy/setup.bash

echo "── ① rmw_cyclonedds (배포판 조립본) ──"
sudo apt install -y ros-jazzy-rmw-cyclonedds-cpp

echo "── ② 유니트리 ROS 메시지 정의 받기·빌드 ──"
mkdir -p ~/uni_ros2_ws/src
cd ~/uni_ros2_ws/src
if [ ! -d unitree_ros2 ]; then
    git clone https://github.com/unitreerobotics/unitree_ros2.git
fi
cd ~/uni_ros2_ws
# 메시지 패키지만 (msg 전용이라 금방 빌드됨)
colcon build --packages-select unitree_go unitree_hg unitree_api

echo "── ③ CycloneDDS 설정 (erasers 템플릿 기반, iface 자동) ──"
IFACE=$(ip -o link show | awk -F': ' '/enx/{print $2; exit}')
if [ -z "$IFACE" ]; then
    echo "  enx 미검출 — 케이블 연결 후 ~/g1_real/cyclonedds_g1.xml 의"
    echo "  NetworkInterface name 을 직접 채우세요."
    IFACE="enx직접입력"
fi
cat > ~/g1_real/cyclonedds_g1.xml <<EOF
<?xml version="1.0" encoding="UTF-8" ?>
<CycloneDDS xmlns="https://cdds.io/config">
    <Domain Id="any">
        <General>
            <Interfaces>
                <NetworkInterface name="${IFACE}" priority="default" multicast="default" />
            </Interfaces>
            <AllowMulticast>spdp</AllowMulticast>
        </General>
        <Internal>
            <MinimumSocketReceiveBufferSize>10MB</MinimumSocketReceiveBufferSize>
        </Internal>
    </Domain>
</CycloneDDS>
EOF
echo "  생성: ~/g1_real/cyclonedds_g1.xml (iface=${IFACE})"

echo ""
echo "완료. 다음: 로봇 켜고 새 터미널에서"
echo "    source ~/g1_real/tapenv.sh"
echo "    ros2 topic list | grep -Ei \"odom|state\""
