#!/usr/bin/env bash
# run_taps.sh — [tapenv 터미널] odom tap + joint tap 동시 실행
# 사용:
#   source ~/g1_real/tapenv.sh
#   bash ~/g1_real/run_taps.sh
# Ctrl+C 한 번에 둘 다 종료.
set -m
python3 ~/g1_real/g1_odom_tap_ros.py &
P1=$!
python3 ~/g1_real/g1_joint_tap.py &
P2=$!
trap "kill $P1 $P2 2>/dev/null" INT TERM
echo "  [run_taps] odom_tap($P1) + joint_tap($P2) 가동 — Ctrl+C 로 동시 종료"
wait
