#!/usr/bin/env bash
# run_relays.sh — [평소 터미널] relay 2종 자동 부활 실행 (launch 우회용 예비)
run_loop() { local n=$1; shift; while true; do "$@"; echo "  [run_relays] $n 종료(code $?) → 1초 후 부활"; sleep 1; done; }
trap 'trap - INT TERM; echo; echo "  [run_relays] 전체 종료"; kill 0' INT TERM
run_loop odom_relay  python3 -u ~/g1_real/g1_odom_relay.py &
run_loop joint_relay python3 -u ~/g1_real/g1_joint_relay.py &
echo "  [run_relays] 가동 (자동 부활 ON)"
wait
