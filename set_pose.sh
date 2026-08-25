#!/usr/bin/env bash
# set_pose.sh — 초기 위치 설정 (TF 타이밍 오류 우회판)
#
# 문제: RViz 의 2D Pose Estimate 는 "지금 이 순간" 타임스탬프를 찍는데,
#   FAST-LIO 의 TF 는 10Hz(최대 100ms 간격)라 그보다 항상 살짝 늦다.
#   AMCL 의 초기위치 처리 경로는 이 어긋남을 기다려주지 않고 즉시
#   거부한다 → "Lookup would require extrapolation into the future".
#
# 해법: 타임스탬프를 0 으로 보낸다. TF 규약에서 0 = "가장 최신 것 사용"
#   이라 타이밍과 무관하게 항상 성공한다.
#
# 사용:
#   bash ~/g1_real/set_pose.sh <바라보는각도(도)>
#   예) bash ~/g1_real/set_pose.sh 0      # 지도 x축 방향
#       bash ~/g1_real/set_pose.sh 90     # 반시계 90도
#
#   실행하면 "클릭 대기" 가 뜬다 → RViz 상단 [Publish Point] 도구를
#   누르고 지도에서 로봇의 실제 위치를 클릭하면 → 그 좌표 + 입력한
#   각도로 초기 위치가 설정된다.

set -u
YAW_DEG=${1:?사용법: bash set_pose.sh <각도(도)>   예: bash set_pose.sh 90}

echo "  RViz 상단 [Publish Point] 도구를 누르고, 지도에서 로봇 위치를 클릭하세요..."
POINT=$(ros2 topic echo /clicked_point --once 2>/dev/null)
X=$(echo "$POINT" | awk '/^  x:/{print $2; exit}')
Y=$(echo "$POINT" | awk '/^  y:/{print $2; exit}')

if [ -z "${X:-}" ] || [ -z "${Y:-}" ]; then
    echo "  [오류] 클릭을 못 받았습니다. RViz 가 떠 있고 Publish Point 로 클릭했는지 확인."
    exit 1
fi

read QZ QW <<< $(python3 -c "
import math
y = math.radians($YAW_DEG)
print(f'{math.sin(y/2):.6f} {math.cos(y/2):.6f}')
")

echo "  설정: x=$X  y=$Y  yaw=${YAW_DEG}도  (stamp=0 → 최신 TF 사용)"

ros2 topic pub --once /initialpose geometry_msgs/msg/PoseWithCovarianceStamped "{
  header: {frame_id: map},
  pose: {
    pose: {
      position: {x: $X, y: $Y, z: 0.0},
      orientation: {z: $QZ, w: $QW}
    },
    covariance: [0.25,0,0,0,0,0,
                 0,0.25,0,0,0,0,
                 0,0,0,0,0,0,
                 0,0,0,0,0,0,
                 0,0,0,0,0,0,
                 0,0,0,0,0,0.068]
  }
}" > /dev/null

echo "  완료 — RViz 에 로봇과 화살표 뭉치가 나타나야 정상입니다."
