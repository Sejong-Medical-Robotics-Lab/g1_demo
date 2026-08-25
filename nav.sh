#!/usr/bin/env bash
# nav.sh — Nav2 launch 를 항상 로그 파일과 함께 실행
#
#   bash ~/g1_real/nav.sh          # 평소처럼 실행, 로그는 자동 저장
#
# 로그 위치:
#   ~/g1_real/logs/nav2_YYYYMMDD_HHMMSS.log   (실행마다 새 파일)
#   ~/g1_real/logs/latest.log                  (항상 최신 실행을 가리킴)
#
# 문제가 생기면 latest.log 만 올리면 된다:
#   화면에 보이는 것과 완전히 동일한 내용이 통째로 들어있다.
#
# 오래된 로그는 최근 20개만 남기고 자동 정리한다.

set -u
LOG_DIR="$HOME/g1_real/logs"
mkdir -p "$LOG_DIR"

LOG="$LOG_DIR/nav2_$(date +%Y%m%d_%H%M%S).log"
ln -sf "$LOG" "$LOG_DIR/latest.log"

# 오래된 로그 정리 (최근 20개 유지)
ls -t "$LOG_DIR"/nav2_*.log 2>/dev/null | tail -n +21 | xargs -r rm -f

echo "  로그 저장: $LOG"
echo "  (최신 링크: $LOG_DIR/latest.log)"
echo

ros2 launch /home/hong/g1_real/g1_nav2_localize.launch.py "$@" 2>&1 | tee "$LOG"
