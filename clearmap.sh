#!/usr/bin/env bash
# clearmap.sh — costmap 을 양쪽(local+global) 모두 청소
#
# 언제 쓰나:
#   - 새 목표를 찍기 직전 (특히 사람이 로봇을 따라다닌 뒤 — 흔적 청소)
#   - "patience exceeded" / "0 poses" 로 멈췄을 때
#   - 유령 장애물이 경로를 막고 있을 때
#
# 사용:  bash ~/g1_real/clearmap.sh

echo "  local costmap 청소..."
ros2 service call /local_costmap/clear_entirely_local_costmap nav2_msgs/srv/ClearEntireCostmap > /dev/null
echo "  global costmap 청소..."
ros2 service call /global_costmap/clear_entirely_global_costmap nav2_msgs/srv/ClearEntireCostmap > /dev/null
echo "  완료 — 이제 목표를 찍으세요."
