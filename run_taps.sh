#!/usr/bin/env bash
# run_taps.sh — [tapenv 터미널] odom tap + joint tap 동시 실행 (자동 부활판)
#
# 사용:
#   source ~/g1_real/tapenv.sh
#   bash ~/g1_real/run_taps.sh
#
# 어느 tap 이든 죽으면 1초 뒤 스스로 되살아난다.
# Ctrl+C 한 번으로 전부(루프+tap) 종료.

run_loop() {
    local name=$1; shift
    while true; do
        "$@"
        echo "  [run_taps] ${name} 종료(code $?) → 1초 후 자동 부활"
        sleep 1
    done
}

trap 'trap - INT TERM; echo; echo "  [run_taps] 전체 종료"; kill 0' INT TERM

run_loop odom_tap  python3 ~/g1_real/g1_odom_tap_ros.py &
run_loop joint_tap python3 ~/g1_real/g1_joint_tap.py &

echo "  [run_taps] odom_tap + joint_tap 가동 (자동 부활 ON) — Ctrl+C 로 동시 종료"
wait
